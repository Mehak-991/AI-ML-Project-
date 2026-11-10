import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import NoReturn

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    DataValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.database.models.user import RefreshToken, User
from app.repositories.users import RefreshTokenRepository, UserRepository
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
    UserUpdateRequest,
)

logger = logging.getLogger(__name__)

# Arbitrary fixed key for the advisory lock that serializes first-account registration.
BOOTSTRAP_LOCK_KEY = 804_120_001

_EMAIL_ADAPTER: TypeAdapter[str] = TypeAdapter(EmailStr)


def create_bootstrap_admin(
    session: Session, email: str, password: str, full_name: str = "Administrator"
) -> User:
    """Create the first administrator. One-time: refuses once any active admin exists.

    This is the only supported way to get an admin on a fresh database (scripts/create_admin.py).
    It never promotes an existing account and never changes an existing password.
    """
    user_repo = UserRepository(session)
    # Same address rules as the login endpoint: an address it rejects could never sign in.
    try:
        email = _EMAIL_ADAPTER.validate_python(email.strip())
    except ValidationError as exc:
        raise DataValidationError("The email address is not valid for sign-in.") from exc
    if session.get_bind().dialect.name == "postgresql":
        # Serializes concurrent runs; the lock lasts until this transaction commits.
        session.execute(select(func.pg_advisory_xact_lock(BOOTSTRAP_LOCK_KEY)))
    has_admin = session.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
    )
    if has_admin:
        raise ConflictError("An active administrator already exists; bootstrap is one-time.")
    normalized = email.lower().strip()
    if user_repo.get_by_email(normalized):
        raise ConflictError(f"A user with email '{normalized}' already exists; it was not changed.")
    security.validate_password_strength(password)
    user = User(
        email=normalized,
        hashed_password=security.hash_password(password),
        full_name=full_name.strip() or "Administrator",
        role="admin",
        is_active=True,
    )
    user_repo.add(user)
    session.commit()
    session.refresh(user)
    return user


def register_user(
    session: Session,
    request: UserRegisterRequest,
    requested_by: User | None = None,
    *,
    allow_first_user_admin: bool = False,
) -> User:
    user_repo = UserRepository(session)
    # Without the explicit development flag nobody becomes admin by registering first.
    is_bootstrap = allow_first_user_admin and user_repo.count() == 0
    if is_bootstrap and session.get_bind().dialect.name == "postgresql":
        # Two simultaneous first registrations must not both become admin. The lock lasts
        # until this transaction commits, so the second one then sees the first user.
        session.execute(select(func.pg_advisory_xact_lock(BOOTSTRAP_LOCK_KEY)))
        is_bootstrap = user_repo.count() == 0
    # Self-registration yields 'viewer'; elevated roles must be granted by an admin.
    if request.role != "viewer" and not is_bootstrap:
        if requested_by is None or requested_by.role != "admin":
            raise PermissionDeniedError(
                "Only administrators can create accounts with the "
                f"'{request.role}' role. Register as 'viewer' and ask an admin to promote you."
            )
    existing = user_repo.get_by_email(request.email)
    if existing:
        raise ConflictError(f"A user with email '{request.email}' already exists.")

    security.validate_password_strength(request.password)
    hashed_pwd = security.hash_password(request.password)

    # First user automatically becomes admin if no users exist
    role = request.role
    if is_bootstrap:
        role = "admin"

    user = User(
        email=request.email.lower().strip(),
        hashed_password=hashed_pwd,
        full_name=request.full_name.strip(),
        role=role,
        is_active=True,
    )
    user_repo.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(
    session: Session, settings: Settings, request: UserLoginRequest
) -> tuple[User, TokenResponse]:
    user_repo = UserRepository(session)
    user = user_repo.get_by_email(request.email)
    stored_hash = user.hashed_password if user else None
    password_ok, upgraded_hash = security.verify_and_rehash(request.password, stored_hash)
    if not password_ok or user is None:
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("User account is deactivated. Contact an administrator.")

    if upgraded_hash is not None and settings.PASSWORD_REHASH_ON_LOGIN:
        # Legacy PBKDF2/bcrypt hash: store the Argon2id one. Committed with the refresh token
        # below, so a failed login can never change what is stored.
        user.hashed_password = upgraded_hash
        logger.info("Upgraded password hash for user %s", user.id)

    access_token = security.create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role}, settings
    )

    raw_refresh_token, token_hash = security.generate_refresh_token()
    expire_date = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    token_repo = RefreshTokenRepository(session)
    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expire_date.isoformat(),
        revoked=False,
    )
    token_repo.add(refresh_record)
    session.commit()

    return user, TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh_token,
        user=UserRead.model_validate(user),
    )


def refresh_access_token(
    session: Session, settings: Settings, request: RefreshTokenRequest
) -> TokenResponse:
    token_hash = security.hash_token(request.refresh_token)
    token_repo = RefreshTokenRepository(session)
    record = token_repo.get_by_hash(token_hash)

    if not record:
        raise AuthenticationError("Invalid or revoked refresh token.")
    if record.revoked:
        _revoke_after_reuse(session, token_repo, record.user_id)

    expires_at = datetime.fromisoformat(record.expires_at)
    if datetime.now(timezone.utc) > expires_at:
        raise AuthenticationError("Refresh token has expired. Please log in again.")

    user = UserRepository(session).get(record.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User is inactive or not found.")

    # Token rotation: revoke used refresh token and issue new pair. The conditional UPDATE
    # lets exactly one of several concurrent requests with the same token win.
    claimed = session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == record.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        session.rollback()
        _revoke_after_reuse(session, token_repo, record.user_id)

    new_access_token = security.create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role}, settings
    )
    raw_new_refresh, new_hash = security.generate_refresh_token()
    new_expire_date = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    new_record = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=new_expire_date.isoformat(),
        revoked=False,
    )
    token_repo.add(new_record)
    session.commit()

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_new_refresh,
        user=UserRead.model_validate(user),
    )



def _revoke_after_reuse(
    session: Session, token_repo: RefreshTokenRepository, user_id: uuid.UUID
) -> NoReturn:
    """A rotated token came back: it was stolen or replayed, so end every session of the user."""
    token_repo.revoke_all_for_user(user_id)
    session.commit()
    logger.warning("Refresh token reuse detected; sessions revoked", extra={"user_id": str(user_id)})
    raise AuthenticationError("Invalid or revoked refresh token.")


def revoke_refresh_token(session: Session, refresh_token: str) -> None:
    token_hash = security.hash_token(refresh_token)
    record = RefreshTokenRepository(session).get_by_hash(token_hash)
    if record:
        record.revoked = True
        session.commit()


def change_password(
    session: Session, user: User, current_password: str, new_password: str
) -> None:
    """Change the user's password and revoke all of *their* refresh tokens.

    Other users' sessions are untouched. Access tokens already issued stay valid
    until they expire (JWT_ACCESS_TOKEN_EXPIRE_MINUTES).
    """
    db_user = UserRepository(session).get(user.id)
    if not db_user:
        raise AuthenticationError("User not found.")
    if not security.verify_password(current_password, db_user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")
    security.validate_password_strength(new_password)
    db_user.hashed_password = security.hash_password(new_password)
    RefreshTokenRepository(session).revoke_all_for_user(user.id)
    session.commit()


def update_user_by_admin(
    session: Session, current_user_id: uuid.UUID, target_user_id: uuid.UUID, request: UserUpdateRequest
) -> User:
    user_repo = UserRepository(session)
    target = user_repo.get(target_user_id)
    if not target:
        raise NotFoundError(f"User {target_user_id} not found.")

    # Prevent self-demotion or self-deactivation if last admin
    if target.role == "admin":
        active_admins = user_repo.count_active_admins()
        if active_admins <= 1:
            if request.is_active is False:
                raise DataValidationError("Cannot deactivate the last active administrator.")
            if request.role is not None and request.role != "admin":
                raise DataValidationError("Cannot change the role of the last active administrator.")

    if request.role is not None:
        target.role = request.role
    if request.is_active is not None:
        target.is_active = request.is_active
        if request.is_active is False:  # security event: end the account's sessions
            RefreshTokenRepository(session).revoke_all_for_user(target.id)
    if request.full_name is not None:
        target.full_name = request.full_name.strip()

    session.commit()
    session.refresh(target)
    return target
