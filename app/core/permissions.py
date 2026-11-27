"""Single source of truth for application roles and what each role may do.

Every protected endpoint declares the *permission* it needs (never a role list), and
this module maps roles to permissions. Authorization is always evaluated against the
role stored in the database for the authenticated user — never against a role claim
in the token or anything submitted by the client.

Roles (exactly three):
- user:        strictly read-only.
- admin:       read all + create/update any employee, delete only the employees they created;
               ML write access; limited user administration (only accounts holding the
               'user' role); no global settings.
- super_admin: everything, including role assignment, account deletion, deployments,
               global settings and the full audit log.
"""

from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


ROLE_VALUES: tuple[str, ...] = tuple(r.value for r in Role)

# Higher rank = more privilege. Used to stop anyone acting on an account above them.
ROLE_RANK: dict[str, int] = {Role.USER: 1, Role.ADMIN: 2, Role.SUPER_ADMIN: 3}


class Permission(StrEnum):
    # Read access to shared, non-sensitive application data.
    EMPLOYEES_READ = "employees:read"
    EMPLOYEES_READ_SENSITIVE = "employees:read_sensitive"
    EMPLOYEES_WRITE = "employees:write"
    # Delete any employee record (super admin).
    EMPLOYEES_DELETE = "employees:delete"
    # Delete only employee records the actor created (admin). Ownership is checked in
    # app.services.employee_service.delete_employee against employees.created_by_id.
    EMPLOYEES_DELETE_OWN = "employees:delete_own"

    ML_READ = "ml:read"
    # Uploading data, training, predicting, experiments, jobs, drift analysis, LLM chat.
    ML_WRITE = "ml:write"
    # Promoting models to (and removing them from) production serving.
    ML_DEPLOY = "ml:deploy"

    USERS_READ = "users:read"
    # Activate/deactivate/rename accounts holding a lower role than the actor.
    USERS_MANAGE = "users:manage"
    # Assign roles, create privileged accounts, delete accounts.
    USERS_ADMINISTER = "users:administer"

    AUDIT_READ = "audit:read"
    AUDIT_READ_ALL = "audit:read_all"

    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"


_USER: frozenset[Permission] = frozenset(
    {Permission.EMPLOYEES_READ, Permission.ML_READ, Permission.SETTINGS_READ}
)
_ADMIN: frozenset[Permission] = _USER | {
    Permission.EMPLOYEES_READ_SENSITIVE,
    Permission.EMPLOYEES_WRITE,
    Permission.EMPLOYEES_DELETE_OWN,
    Permission.ML_WRITE,
    Permission.USERS_READ,
    Permission.USERS_MANAGE,
    Permission.AUDIT_READ,
}
_SUPER_ADMIN: frozenset[Permission] = frozenset(Permission)

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    Role.USER: _USER,
    Role.ADMIN: frozenset(_ADMIN),
    Role.SUPER_ADMIN: _SUPER_ADMIN,
}

# Permissions that change state. Blocked for everyone but super admins in maintenance mode.
WRITE_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.EMPLOYEES_WRITE,
        Permission.EMPLOYEES_DELETE,
        Permission.EMPLOYEES_DELETE_OWN,
        Permission.ML_WRITE,
        Permission.ML_DEPLOY,
        Permission.USERS_MANAGE,
        Permission.USERS_ADMINISTER,
    }
)


def permissions_for(role: str | None) -> frozenset[Permission]:
    """Permissions of a role; unknown or missing roles get none (fail closed)."""
    if role is None:
        return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(role: str | None, permission: Permission) -> bool:
    return permission in permissions_for(role)


def role_rank(role: str | None) -> int:
    return ROLE_RANK.get(role or "", 0)


def is_super_admin(role: str | None) -> bool:
    return role == Role.SUPER_ADMIN
