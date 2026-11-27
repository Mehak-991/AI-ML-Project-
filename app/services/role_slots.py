"""One-time sign-up slots for the privileged roles.

Rule: anyone may create any number of 'user' accounts, but an 'admin' or 'super_admin'
account can be created through public sign-up only once per role. The first time an account
with that role is created — by sign-up, by a super admin, by promotion or by the CLI — the
role's slot is permanently marked as used in `system_settings` (key `signup_slot:<role>`).
Deactivating or deleting that account later does NOT reopen the slot.

The marker row's primary key makes the claim race-safe: two simultaneous sign-ups for the
same slot cannot both commit (the second hits a unique violation and gets a 409).
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.core.permissions import Role
from app.database.models.system_setting import SystemSetting
from app.database.models.user import User

PRIVILEGED_ROLES: tuple[str, ...] = (Role.ADMIN.value, Role.SUPER_ADMIN.value)
ROLE_LABEL = {Role.ADMIN.value: "Admin", Role.SUPER_ADMIN.value: "Super Admin"}


def _key(role: str) -> str:
    return f"signup_slot:{role}"


def is_open(session: Session, role: str) -> bool:
    """True if a public sign-up may still create an account with `role`."""
    if role not in PRIVILEGED_ROLES:
        return True
    if session.get(SystemSetting, _key(role)) is not None:
        return False
    # Databases that existed before slot tracking: an existing account already used the slot.
    existing = session.scalar(select(func.count()).select_from(User).where(User.role == role))
    return not existing


def available_roles(session: Session | None) -> list[str]:
    """Roles a public sign-up form may offer right now ('user' is always available)."""
    if session is None:
        return [Role.USER.value]
    return [Role.USER.value, *(r for r in PRIVILEGED_ROLES if is_open(session, r))]


def ensure_open(session: Session, role: str) -> None:
    if not is_open(session, role):
        raise PermissionDeniedError(
            f"The {ROLE_LABEL[role]} account has already been registered. It can be created "
            "only once; sign in with that account instead."
        )


def mark_used(session: Session, role: str, user: User, *, strict: bool = False) -> None:
    """Permanently close the slot for `role` (no-op for 'user' or an already-closed slot).

    strict=True is used by public sign-up: if another request claimed the slot first, the
    unique key on system_settings.key makes this transaction fail with a 409.
    """
    if role not in PRIVILEGED_ROLES:
        return
    key = _key(role)
    if not strict and session.get(SystemSetting, key) is not None:
        return
    session.add(
        SystemSetting(
            key=key,
            value={"claimed_by": str(user.id), "at": datetime.now(UTC).isoformat()},
            updated_by_id=None,
        )
    )
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            f"The {ROLE_LABEL[role]} account was registered by another request just now."
        ) from exc
