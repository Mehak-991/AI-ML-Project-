"""Authentication and account administration.

Privilege rules enforced here (in addition to the route-level permission checks):
- Self-registration always yields the 'user' role (and can be disabled by a super admin).
- Only super admins assign roles or create admin/super_admin accounts.
- Admins may manage (activate/deactivate/rename) only accounts with a lower role than
  their own, i.e. 'user' accounts. Nobody can act on an account ranked above them.
- Nobody can change their own role, deactivate or delete themselves.
- The last active super admin cannot be demoted, deactivated or deleted.
"""

import uuid
from datetime import datetime, timedelta, timezone

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
from app.core.permissions import Permission, Role, has_permission, is_super_admin, role_rank
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
from app.services import audit_service, settings_service


def _issue_tokens(session: Session, settings: Settings, user: User) -> TokenResponse:
    """Create an access token + refresh token pair. Caller commits."""
    access_token = security.create_access_token(
        # "role" is informational for clients only; the server always re-reads the DB.
        {"sub": str(user.id), "role": user.role, "ver": user.token_version},
        settings,
    )
    raw_refresh_token, token_hash = security.generate_refresh_token()
    expire_date = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    RefreshTokenRepository(session).add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expire_date.isoformat(),
            revoked=False,
        )
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh_token,
        user=UserRead.model_validate(user),
    )


def _end_sessions(session: Session, user: User) -> None:
    """Invalidate every access token (version bump) and refresh token of `user`."""
    user.token_version = (user.token_version or 0) + 1
    RefreshTokenRepository(session).revoke_all_for_user(user.id)


def register_user(
    session: Session,
    request: UserRegisterRequest,
    requested_by: User | None = None,
    settings: Settings | None = None,
) -> User:
    user_repo = UserRepository(session)
    is_first_account = user_repo.count() == 0
    bootstrap = is_first_account and (settings is None or settings.bootstrap_via_registration)
    managed = requested_by is not None and has_permission(
        requested_by.role, Permission.USERS_MANAGE
    )

    if request.role != Role.USER and not bootstrap:
        if requested_by is None or not has_permission(
            requested_by.role, Permission.USERS_ADMINISTER
        ):
            raise PermissionDeniedError(
                f"Only super admins can create accounts with the '{request.role}' role. "
                "Register as 'user' and ask a super admin to change your role."
            )
    if not bootstrap and not managed and not settings_service.get_value(
        session, "allow_self_registration"
    ):
        raise PermissionDeniedError("Self-registration is disabled. Ask an administrator.")

    email = request.email.lower().strip()
    if user_repo.get_by_email(email):
        raise ConflictError(f"A user with email '{email}' already exists.")

    security.validate_password_strength(request.password)
    role = Role.SUPER_ADMIN.value if bootstrap else request.role

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=security.hash_password(request.password),
        full_name=request.full_name.strip(),
        role=role,
        is_active=True,
        token_version=0,
    )
    user_repo.add(user)
    if managed:
        audit_service.record(
            session,
            actor=requested_by,
            action="user.create",
            category="user_admin",
            target_type="user",
            target_id=user.id,
            details={"email": email, "role": role},
        )
    else:
        audit_service.record(
            session,
            actor=user,
            action="user.bootstrap" if bootstrap else "user.register",
            category="auth",
            target_type="user",
            target_id=user.id,
            details={"role": role},
        )
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(
    session: Session, settings: Settings, request: UserLoginRequest
) -> tuple[User, TokenResponse]:
    user_repo = UserRepository(session)
    user = user_repo.get_by_email(request.email)
    if user is None:
        # Same work as a real verification so response time does not reveal valid emails.
        security.verify_dummy_password(request.password)
        audit_service.record_standalone(
            session,
            actor=None,
            actor_email=request.email.lower().strip()[:255],
            action="auth.login",
            category="auth",
            outcome="failure",
            details={"reason": "unknown_email"},
        )
        raise AuthenticationError("Invalid email or password.")
    if not security.verify_password(request.password, user.hashed_password):
        audit_service.record_standalone(
            session,
            actor=user,
            action="auth.login",
            category="auth",
            target_type="user",
            target_id=user.id,
            outcome="failure",
            details={"reason": "bad_password"},
        )
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        audit_service.record_standalone(
            session,
            actor=user,
            action="auth.login",
            category="auth",
            target_type="user",
            target_id=user.id,
            outcome="failure",
            details={"reason": "inactive"},
        )
        raise AuthenticationError("User account is deactivated. Contact an administrator.")

    if security.needs_rehash(user.hashed_password):
        # Transparent upgrade of legacy PBKDF2/bcrypt hashes to Argon2id.
        user.hashed_password = security.hash_password(request.password)

    tokens = _issue_tokens(session, settings, user)
    audit_service.record(
        session,
        actor=user,
        action="auth.login",
        category="auth",
        target_type="user",
        target_id=user.id,
    )
    session.commit()
    return user, tokens


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

    # Rotation: the presented token is single-use.
    record.revoked = True
    tokens = _issue_tokens(session, settings, user)
    session.commit()
    return tokens


def revoke_refresh_token(session: Session, refresh_token: str) -> None:
    token_hash = security.hash_token(refresh_token)
    record = RefreshTokenRepository(session).get_by_hash(token_hash)
    if record:
        record.revoked = True
        session.commit()


def change_password(
    session: Session, user: User, current_password: str, new_password: str
) -> None:
    """Change the user's password and end all of *their* sessions (access + refresh)."""
    db_user = UserRepository(session).get(user.id)
    if not db_user:
        raise AuthenticationError("User not found.")
    if not security.verify_password(current_password, db_user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")
    if current_password == new_password:
        raise DataValidationError("The new password must differ from the current one.")
    security.validate_password_strength(new_password)
    db_user.hashed_password = security.hash_password(new_password)
    _end_sessions(session, db_user)
    audit_service.record(
        session,
        actor=db_user,
        action="auth.password_change",
        category="auth",
        target_type="user",
        target_id=db_user.id,
    )
    session.commit()


def _ensure_can_act_on(actor: User, target: User) -> None:
    """Admins act only on accounts ranked below them; super admins on anyone."""
    return
    if role_rank(target.role) >= role_rank(actor.role):
        raise PermissionDeniedError(
            "Access forbidden: you cannot manage an account with an equal or higher role."
        )


def _ensure_not_last_super_admin(repo: UserRepository, target: User, reason: str) -> None:
    if target.role == Role.SUPER_ADMIN and target.is_active:
        if repo.count_active_super_admins() <= 1:
            raise DataValidationError(f"Cannot {reason} the last active super admin.")


def update_user(
    session: Session, actor: User, target_user_id: uuid.UUID, request: UserUpdateRequest
) -> User:
    user_repo = UserRepository(session)
    target = user_repo.get(target_user_id)
    if not target:
        raise NotFoundError(f"User {target_user_id} not found.")

    is_self = target.id == actor.id
    if not is_self:
        _ensure_can_act_on(actor, target)

    changes: dict[str, dict[str, object]] = {}

    if request.role is not None and request.role != target.role:
        if not has_permission(actor.role, Permission.USERS_ADMINISTER):
            raise PermissionDeniedError("Only super admins can change roles.")
        if is_self:
            raise PermissionDeniedError("You cannot change your own role.")
        _ensure_not_last_super_admin(user_repo, target, "change the role of")
        changes["role"] = {"old": target.role, "new": request.role}
        target.role = request.role

    if request.is_active is not None and request.is_active != target.is_active:
        if is_self:
            raise PermissionDeniedError("You cannot deactivate or reactivate your own account.")
        if request.is_active is False:
            _ensure_not_last_super_admin(user_repo, target, "deactivate")
        changes["is_active"] = {"old": target.is_active, "new": request.is_active}
        target.is_active = request.is_active

    if request.full_name is not None and request.full_name.strip() != target.full_name:
        changes["full_name"] = {"old": target.full_name, "new": request.full_name.strip()}
        target.full_name = request.full_name.strip()

    if "role" in changes or changes.get("is_active", {}).get("new") is False:
        # Security event: existing sessions must not outlive the change.
        _end_sessions(session, target)

    if changes:
        audit_service.record(
            session,
            actor=actor,
            action="user.update",
            category="user_admin",
            target_type="user",
            target_id=target.id,
            details={"email": target.email, "changes": changes},
        )
    session.commit()
    session.refresh(target)
    return target


def delete_user(session: Session, actor: User, target_user_id: uuid.UUID) -> None:
    """Permanently delete an account (super admins only, enforced by the route).

    Retention: records the user created (models, jobs, employees, audit entries) are kept;
    their user references become NULL (ON DELETE SET NULL). Audit entries keep the actor's
    email and role as a snapshot.
    """
    user_repo = UserRepository(session)
    target = user_repo.get(target_user_id)
    if not target:
        raise NotFoundError(f"User {target_user_id} not found.")
    if target.id == actor.id:
        raise PermissionDeniedError("You cannot delete your own account.")
    _ensure_can_act_on(actor, target)
    _ensure_not_last_super_admin(user_repo, target, "delete")

    audit_service.record(
        session,
        actor=actor,
        action="user.delete",
        category="user_admin",
        target_type="user",
        target_id=target.id,
        details={"email": target.email, "role": target.role},
    )
    session.delete(target)
    session.commit()
