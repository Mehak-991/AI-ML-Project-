from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError, DataValidationError, NotFoundError
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


def register_user(session: Session, request: UserRegisterRequest) -> User:
    user_repo = UserRepository(session)
    existing = user_repo.get_by_email(request.email)
    if existing:
        raise ConflictError(f"A user with email '{request.email}' already exists.")

    security.validate_password_strength(request.password)
    hashed_pwd = security.hash_password(request.password)

    # First user automatically becomes admin if no users exist
    role = request.role
    if user_repo.count() == 0:
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
    if not user or not security.verify_password(request.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("User account is deactivated. Contact an administrator.")

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

    if not record or record.revoked:
        raise AuthenticationError("Invalid or revoked refresh token.")

    expires_at = datetime.fromisoformat(record.expires_at)
    if datetime.now(timezone.utc) > expires_at:
        raise AuthenticationError("Refresh token has expired. Please log in again.")

    user = UserRepository(session).get(record.user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User is inactive or not found.")

    # Token rotation: revoke used refresh token and issue new pair
    record.revoked = True

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
    if not security.verify_password(current_password, user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")
    security.validate_password_strength(new_password)
    user.hashed_password = security.hash_password(new_password)
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
