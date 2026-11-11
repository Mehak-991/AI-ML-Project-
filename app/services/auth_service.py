import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import NoReturn

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.permissions import Permission, Role, effective_role, has_permission
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    DataValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.database.models.user import RefreshToken, User
from app.repositories.users import RefreshTokenRepository, UserRepository
from app.services import audit_service
from app.schemas.auth import (
    SelfUpdateRequest,
    UserCreateRequest,
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


def _stored_role_name(role: str, settings: Settings) -> str:
    """The value written to ``users.role``.

    During the expand window (code deployed, migration 0014 not yet applied or rollback still
    wanted) ``RBAC_STORE_LEGACY_VIEWER`` keeps new read-only accounts stored as ``viewer`` so
    previous releases can still read them. The effective role is ``user`` either way.
    """
    if role == "user" and settings.RBAC_STORE_LEGACY_VIEWER:
        return "viewer"
    return role


def register_user(session: Session, request: UserRegisterRequest, settings: Settings) -> User:
    """Public self-registration. Always creates a read-only ``user``; there is no way to ask
    for anything else (the request schema has no role field)."""
    user_repo = UserRepository(session)
    if user_repo.get_by_email(request.email):
        raise ConflictError(f"A user with email '{request.email}' already exists.")

    security.validate_password_strength(request.password)
    user = User(
        email=request.email.lower().strip(),
        hashed_password=security.hash_password(request.password),
        full_name=request.full_name.strip(),
        role=_stored_role_name("user", settings),
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


# --- User administration (superadmin) ------------------------------------------------------------


def _require(actor: User, permission: Permission) -> None:
    """Defence in depth: the routes already require the permission; the service checks again so
    no caller (CLI, test, future route) can reach these operations without it."""
    if not has_permission(actor.role, permission):
        raise PermissionDeniedError(f"Access forbidden: the '{permission.value}' permission is required.")


def _get_target(session: Session, target_id: uuid.UUID) -> User:
    target = UserRepository(session).get(target_id)
    if target is None:
        raise NotFoundError(f"User {target_id} not found.")
    return target


def _is_superadmin(user: User) -> bool:
    return effective_role(user.role) is Role.SUPERADMIN


def _guard_last_superadmin(session: Session, target: User, action: str) -> None:
    """Refuse to remove the last active superadmin.

    Locks every active superadmin row first, then re-reads the target, so two concurrent requests
    that would each leave one superadmin cannot both succeed: the second one sees the result of
    the first and is refused. Called before any change that would stop ``target`` from being an
    active superadmin.
    """
    active = UserRepository(session).lock_active_superadmins()
    session.refresh(target)
    if _is_superadmin(target) and target.is_active and len(active) <= 1:
        raise ConflictError(
            f"Cannot {action} the last active superadmin. Grant superadmin to another account first."
        )


def create_user(
    session: Session,
    actor: User,
    request: UserCreateRequest,
    settings: Settings,
    context: audit_service.AuditContext | None = None,
) -> User:
    _require(actor, Permission.USERS_MANAGE)
    _require(actor, Permission.ROLES_ASSIGN)
    repo = UserRepository(session)
    if repo.get_by_email(request.email):
        raise ConflictError(f"A user with email '{request.email}' already exists.")
    security.validate_password_strength(request.password)
    user = User(
        email=request.email.lower().strip(),
        hashed_password=security.hash_password(request.password),
        full_name=request.full_name.strip(),
        role=_stored_role_name(request.role, settings),
        is_active=True,
    )
    repo.add(user)
    session.flush()
    audit_service.record(
        session,
        action=audit_service.ACTION_USER_CREATED,
        actor=actor,
        target=user,
        after=audit_service.user_snapshot(user),
        context=context,
    )
    session.commit()
    session.refresh(user)
    return user


def update_user(
    session: Session,
    actor: User,
    target_id: uuid.UUID,
    request: UserUpdateRequest,
    settings: Settings,
    context: audit_service.AuditContext | None = None,
) -> User:
    """Change a user's role (between ``user`` and ``admin``), active flag or display name.

    One transaction: the change, the last-superadmin check and the audit entries commit together.
    Granting or revoking superadmin has its own operations below.
    """
    _require(actor, Permission.USERS_MANAGE)
    target = _get_target(session, target_id)
    changing_status = request.is_active is not None and request.is_active != target.is_active
    new_role = request.role
    current_effective = effective_role(target.role)

    if target.id == actor.id and (new_role is not None or request.is_active is not None):
        raise PermissionDeniedError("You cannot change your own role or active status.")

    role_change = new_role is not None and (
        current_effective is None or current_effective.value != new_role
    )
    if role_change:
        _require(actor, Permission.ROLES_ASSIGN)
        if _is_superadmin(target):
            raise ConflictError("This account is a superadmin; revoke superadmin first.")

    if changing_status and request.is_active is False and _is_superadmin(target):
        _guard_last_superadmin(session, target, "deactivate")

    before = audit_service.user_snapshot(target)
    if role_change:
        target.role = _stored_role_name(new_role, settings)
        audit_service.record(
            session,
            action=audit_service.ACTION_ROLE_CHANGED,
            actor=actor,
            target=target,
            before={"role": before["role"]},
            after={"role": target.role},
            context=context,
        )
    if changing_status:
        target.is_active = bool(request.is_active)
        if not target.is_active:  # security event: end the account's sessions
            RefreshTokenRepository(session).revoke_all_for_user(target.id)
        audit_service.record(
            session,
            action=(
                audit_service.ACTION_REACTIVATED
                if target.is_active
                else audit_service.ACTION_DEACTIVATED
            ),
            actor=actor,
            target=target,
            before={"is_active": before["is_active"]},
            after={"is_active": target.is_active},
            context=context,
        )
    if request.full_name is not None and request.full_name.strip() != target.full_name:
        target.full_name = request.full_name.strip()
        audit_service.record(
            session,
            action=audit_service.ACTION_PROFILE_UPDATED,
            actor=actor,
            target=target,
            before={"full_name": before["full_name"]},
            after={"full_name": target.full_name},
            context=context,
        )

    session.commit()
    session.refresh(target)
    return target


def grant_superadmin(
    session: Session,
    actor: User,
    target_id: uuid.UUID,
    context: audit_service.AuditContext | None = None,
) -> User:
    """Only an existing superadmin can do this (the permission is held by no other role)."""
    _require(actor, Permission.SUPERADMIN_GRANT)
    target = _get_target(session, target_id)
    if not target.is_active:
        raise ConflictError("Only an active account can be made a superadmin.")
    if _is_superadmin(target):
        raise ConflictError("This account is already a superadmin.")
    before = audit_service.user_snapshot(target)
    target.role = "superadmin"
    audit_service.record(
        session,
        action=audit_service.ACTION_SUPERADMIN_GRANTED,
        actor=actor,
        target=target,
        before={"role": before["role"]},
        after={"role": "superadmin"},
        context=context,
    )
    session.commit()
    session.refresh(target)
    return target


def revoke_superadmin(
    session: Session,
    actor: User,
    target_id: uuid.UUID,
    context: audit_service.AuditContext | None = None,
) -> User:
    """Demote a superadmin to admin. The last active superadmin can never be demoted."""
    _require(actor, Permission.SUPERADMIN_GRANT)
    target = _get_target(session, target_id)
    if target.id == actor.id:
        raise PermissionDeniedError("You cannot revoke your own superadmin role.")
    _guard_last_superadmin(session, target, "demote")
    if not _is_superadmin(target):
        raise ConflictError("This account is not a superadmin.")
    target.role = "admin"
    audit_service.record(
        session,
        action=audit_service.ACTION_SUPERADMIN_REVOKED,
        actor=actor,
        target=target,
        before={"role": "superadmin"},
        after={"role": "admin"},
        context=context,
    )
    session.commit()
    session.refresh(target)
    return target


def _owned_resource_counts(session: Session, user_id: uuid.UUID) -> dict[str, int]:
    from app.database.models.dataset import Dataset
    from app.database.models.deployment import PredictionLog
    from app.database.models.experiment import Experiment
    from app.database.models.job import Job
    from app.database.models.ml_model import MLModel

    owned_by = {
        "datasets": (Dataset, Dataset.owner_id),
        "models": (MLModel, MLModel.owner_id),
        "experiments": (Experiment, Experiment.created_by_id),
        "jobs": (Job, Job.created_by_id),
        "prediction_logs": (PredictionLog, PredictionLog.requested_by_id),
    }
    return {
        name: session.scalar(select(func.count()).select_from(model).where(column == user_id)) or 0
        for name, (model, column) in owned_by.items()
    }


def delete_user(
    session: Session,
    actor: User,
    target_id: uuid.UUID,
    confirm_email: str,
    context: audit_service.AuditContext | None = None,
) -> None:
    """Hard-delete an account. Deactivation is the default; this is deliberately narrow:

    the account must already be deactivated, must not be a superadmin, must own no resources,
    and the caller must type its email address as explicit confirmation.
    """
    _require(actor, Permission.USERS_MANAGE)
    target = _get_target(session, target_id)
    if target.id == actor.id:
        raise PermissionDeniedError("You cannot delete your own account.")
    if _is_superadmin(target):
        raise ConflictError("A superadmin cannot be deleted; revoke superadmin first.")
    if target.is_active:
        raise ConflictError("Deactivate the account first; deletion is only for deactivated accounts.")
    if confirm_email.strip().lower() != target.email.lower():
        raise DataValidationError("The confirmation email does not match the account.")
    owned = {name: n for name, n in _owned_resource_counts(session, target.id).items() if n}
    if owned:
        raise ConflictError(
            "This account owns resources and cannot be deleted; keep it deactivated instead: "
            + ", ".join(f"{n} {name}" for name, n in owned.items())
        )
    audit_service.record(
        session,
        action=audit_service.ACTION_DELETED,
        actor=actor,
        target=target,
        before=audit_service.user_snapshot(target),
        context=context,
    )
    session.delete(target)
    session.commit()


def update_own_profile(
    session: Session,
    user: User,
    request: SelfUpdateRequest,
    context: audit_service.AuditContext | None = None,
) -> User:
    """Display name only. A role or status can never be changed through this path."""
    _require(user, Permission.PROFILE_MANAGE)
    db_user = _get_target(session, user.id)
    new_name = request.full_name.strip()
    if new_name != db_user.full_name:
        before = db_user.full_name
        db_user.full_name = new_name
        audit_service.record(
            session,
            action=audit_service.ACTION_PROFILE_UPDATED,
            actor=db_user,
            target=db_user,
            before={"full_name": before},
            after={"full_name": new_name},
            context=context,
        )
        session.commit()
        session.refresh(db_user)
    return db_user


# --- Server-side bootstrap and recovery (used by the CLIs; never exposed through the API) ----------


def bootstrap_superadmin(
    session: Session,
    *,
    email: str,
    password: str | None = None,
    promote_existing: bool = False,
    full_name: str = "Superadmin",
    actor_label: str = "cli",
) -> User:
    """Create the first superadmin, or promote one explicit existing account. One-time: refuses
    once any active superadmin exists. Writes an audit entry. Never changes a password.
    """
    repo = UserRepository(session)
    if session.get_bind().dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(BOOTSTRAP_LOCK_KEY)))
    if repo.lock_active_superadmins():
        raise ConflictError("An active superadmin already exists; bootstrap is one-time.")
    try:
        normalized = _EMAIL_ADAPTER.validate_python(email.strip()).lower()
    except ValidationError as exc:
        raise DataValidationError("The email address is not valid for sign-in.") from exc

    existing = repo.get_by_email(normalized)
    if promote_existing:
        if existing is None:
            raise NotFoundError(f"No account with email '{normalized}' exists; nothing was changed.")
        if not existing.is_active:
            raise ConflictError("That account is deactivated; reactivate it before promoting it.")
        before_role = existing.role
        existing.role = "superadmin"
        user = existing
        detail = "promoted existing account"
    else:
        if existing is not None:
            raise ConflictError(f"A user with email '{normalized}' already exists; it was not changed.")
        if not password:
            raise DataValidationError("A password is required to create a new account.")
        security.validate_password_strength(password)
        user = User(
            email=normalized,
            hashed_password=security.hash_password(password),
            full_name=full_name.strip() or "Superadmin",
            role="superadmin",
            is_active=True,
        )
        repo.add(user)
        session.flush()
        before_role = None
        detail = "created new account"
    audit_service.record(
        session,
        action=audit_service.ACTION_CLI_BOOTSTRAP,
        actor_label=actor_label,
        target=user,
        before={"role": before_role} if before_role else None,
        after={"role": "superadmin"},
        detail=detail,
    )
    session.commit()
    session.refresh(user)
    return user


def reset_password_by_operator(
    session: Session, *, email: str, new_password: str, actor_label: str = "cli"
) -> User:
    """Recovery when a superadmin password is lost. Revokes the account's sessions; audited."""
    target = UserRepository(session).get_by_email(email)
    if target is None:
        raise NotFoundError("No account with that email exists; nothing was changed.")
    security.validate_password_strength(new_password)
    target.hashed_password = security.hash_password(new_password)
    RefreshTokenRepository(session).revoke_all_for_user(target.id)
    audit_service.record(
        session,
        action=audit_service.ACTION_CLI_PASSWORD_RESET,
        actor_label=actor_label,
        target=target,
        detail="password reset by operator; sessions revoked",
    )
    session.commit()
    session.refresh(target)
    return target
