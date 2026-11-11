"""Role-based access control: the single source of truth for roles and permissions.

Exactly three application roles exist: ``user`` (read-only), ``admin`` and ``superadmin``.

The permission registry below decides what each role may do. Routes never compare role names;
they declare a :class:`Permission` (``require_permission``) or are explicitly public. The frontend
receives the computed list from ``GET /auth/me`` instead of keeping its own copy.

Expand/migrate/contract rollout
-------------------------------
Databases created before RBAC v2 store ``viewer``, ``ml_engineer`` and ``admin``. This module
reads both vocabularies (``effective_role``) so the code can be deployed before migration
``0014`` runs and keeps working afterwards. Legacy values never grant more than they did before:

* ``viewer``      -> ``user``
* ``ml_engineer`` -> ``user`` (least privilege until an operator reviews the account; migration
  ``0014`` refuses to run while such accounts exist without an explicit mapping)
* anything else   -> no role, so no permissions (deny by default)

The legacy reader is removed in the contract release.
"""

from __future__ import annotations

import enum
import logging

logger = logging.getLogger("app.auth")


class Role(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class Permission(str, enum.Enum):
    # Reading platform resources (datasets, models, experiments, jobs, monitoring, drift,
    # prediction history). Object-level scoping still applies for non-privileged roles.
    RESOURCES_READ = "resources:read"
    # Running inference and explanations (predict, SHAP, LIME, NLP helpers). Read-class: these
    # change no managed resource.
    PREDICT = "predict:run"
    # Creating or changing managed ML resources: dataset upload, training, experiments, jobs,
    # drift analysis, ground truth, LLM helpers.
    ML_OPERATE = "ml:operate"
    # Deploying and undeploying models.
    DEPLOYMENTS_MANAGE = "deployments:manage"
    # Own profile and password.
    PROFILE_MANAGE = "profile:manage"
    # User administration (superadmin only).
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    ROLES_ASSIGN = "roles:assign"
    SUPERADMIN_GRANT = "superadmin:grant"
    # Security surfaces (superadmin only).
    AUDIT_READ = "audit:read"
    SETTINGS_READ = "settings:read"


_USER_PERMISSIONS = frozenset(
    {Permission.RESOURCES_READ, Permission.PREDICT, Permission.PROFILE_MANAGE}
)
_ADMIN_PERMISSIONS = _USER_PERMISSIONS | {Permission.ML_OPERATE, Permission.DEPLOYMENTS_MANAGE}

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.USER: _USER_PERMISSIONS,
    Role.ADMIN: frozenset(_ADMIN_PERMISSIONS),
    # The superadmin holds every permission, including any added later.
    Role.SUPERADMIN: frozenset(Permission),
}

# Values that may still be stored by databases that predate RBAC v2.
LEGACY_ROLE_ALIASES: dict[str, Role] = {
    "viewer": Role.USER,
    "ml_engineer": Role.USER,
}
LEGACY_ROLE_NAMES = frozenset(LEGACY_ROLE_ALIASES)
CURRENT_ROLE_NAMES = frozenset(role.value for role in Role)


def effective_role(stored: str | None) -> Role | None:
    """The role a stored value stands for, or None when it is unknown (which grants nothing)."""
    if not stored:
        return None
    try:
        return Role(stored)
    except ValueError:
        pass
    legacy = LEGACY_ROLE_ALIASES.get(stored)
    if legacy is not None:
        if stored == "ml_engineer":
            logger.warning(
                "Account has the legacy role 'ml_engineer'; treated as 'user' until reviewed "
                "(migration 0014 requires an explicit mapping)."
            )
        return legacy
    logger.error("Unknown stored role %r; granting no permissions.", stored)
    return None


def permissions_for(stored_role: str | None) -> frozenset[Permission]:
    role = effective_role(stored_role)
    return ROLE_PERMISSIONS[role] if role is not None else frozenset()


def has_permission(stored_role: str | None, permission: Permission) -> bool:
    return permission in permissions_for(stored_role)


def has_full_resource_access(stored_role: str | None) -> bool:
    """True for roles that see and use every managed resource regardless of ownership."""
    return effective_role(stored_role) in (Role.ADMIN, Role.SUPERADMIN)


def permission_names(stored_role: str | None) -> list[str]:
    """Stable, sorted permission strings for API responses."""
    return sorted(permission.value for permission in permissions_for(stored_role))
