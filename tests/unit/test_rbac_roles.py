"""Three-role RBAC (user / admin / super_admin) verified end-to-end through the API.

Uses real JWT authentication (no mock-user fallback); only the database is SQLite.
Covers: the permission matrix, employee CRUD, sensitive-field filtering, privilege
escalation and mass-assignment attempts, token revocation, audit logs, global settings
and maintenance mode.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    has_permission,
    permissions_for,
)
from app.database.models import AuditLog, User
from app.database.session import get_db
from app.main import create_app

API = "/api/v1"
PASSWORD = "Password123!"


# --- fixtures ----------------------------------------------------------------------------


@pytest.fixture
def rbac_settings(make_settings):
    return make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False)


@pytest.fixture
def client(rbac_settings, session_factory) -> Iterator[TestClient]:
    app = create_app(rbac_settings)

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def h(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def code(response) -> str:
    return response.json()["error"]["code"]


@pytest.fixture
def roles(client) -> dict[str, dict]:
    """super (bootstrap super_admin), super2, admin, admin2, user — all logged in."""
    assert client.post(
        f"{API}/auth/register", json={"email": "super@x.com", "password": PASSWORD}
    ).status_code == 201
    root = _login(client, "super@x.com")
    assert root["user"]["role"] == "super_admin"
    for email, role in (
        ("super2@x.com", "super_admin"),
        ("admin@x.com", "admin"),
        ("admin2@x.com", "admin"),
        ("user@x.com", "user"),
    ):
        r = client.post(
            f"{API}/auth/register",
            json={"email": email, "password": PASSWORD, "role": role},
            headers=h(root),
        )
        assert r.status_code == 201, r.text
    return {
        "super": root,
        "super2": _login(client, "super2@x.com"),
        "admin": _login(client, "admin@x.com"),
        "admin2": _login(client, "admin2@x.com"),
        "user": _login(client, "user@x.com"),
    }


EMPLOYEE = {
    "employee_code": "emp-001",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "Ada@Example.com",
    "department": "Engineering",
    "job_title": "Analyst",
    "hire_date": "2024-03-01",
    "phone": "+44 20 7946 0000",
    "salary": "85000.00",
}


@pytest.fixture
def employee(client, roles) -> dict:
    r = client.post(f"{API}/employees", json=EMPLOYEE, headers=h(roles["admin"]))
    assert r.status_code == 201, r.text
    return r.json()


# --- permission matrix (pure) -------------------------------------------------------------


def test_exactly_three_roles() -> None:
    assert {r.value for r in Role} == {"user", "admin", "super_admin"}
    assert set(ROLE_PERMISSIONS) == {"user", "admin", "super_admin"}


def test_user_role_is_strictly_read_only() -> None:
    granted = permissions_for("user")
    assert granted == {Permission.EMPLOYEES_READ, Permission.ML_READ, Permission.SETTINGS_READ}
    assert not any(p.value.endswith((":write", ":delete", ":deploy", ":manage")) for p in granted)


def test_admin_permissions_exclude_super_admin_powers() -> None:
    for power in (
        Permission.USERS_ADMINISTER,
        Permission.SETTINGS_WRITE,
        Permission.EMPLOYEES_DELETE,
        Permission.ML_DEPLOY,
        Permission.AUDIT_READ_ALL,
    ):
        assert not has_permission("admin", power)
    assert has_permission("admin", Permission.EMPLOYEES_WRITE)
    assert has_permission("admin", Permission.ML_WRITE)


def test_super_admin_has_every_permission_and_roles_are_nested() -> None:
    assert permissions_for("super_admin") == frozenset(Permission)
    assert permissions_for("user") < permissions_for("admin") < permissions_for("super_admin")


@pytest.mark.parametrize("role", [None, "", "viewer", "ml_engineer", "SUPER_ADMIN", "root"])
def test_unknown_roles_get_nothing(role) -> None:
    assert permissions_for(role) == frozenset()


# --- authentication -------------------------------------------------------------------------


def test_passwords_are_hashed_with_argon2id(client, roles, session_factory) -> None:
    with session_factory() as session:
        stored = session.query(User).filter_by(email="user@x.com").one().hashed_password
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_production_argon2_parameters() -> None:
    from argon2 import PasswordHasher, Type

    # Tests swap in a cheap hasher (conftest); the shipped parameters must stay strong.
    assert security.ARGON2_TIME_COST >= 3
    assert security.ARGON2_MEMORY_COST_KIB >= 64 * 1024
    real = PasswordHasher(
        time_cost=security.ARGON2_TIME_COST,
        memory_cost=security.ARGON2_MEMORY_COST_KIB,
        parallelism=security.ARGON2_PARALLELISM,
    )
    assert real.type is Type.ID
    assert real.hash("x").startswith("$argon2id$v=19$m=65536,t=3,p=4$")


def test_legacy_pbkdf2_hash_is_upgraded_on_login(client, session_factory) -> None:
    from passlib.hash import pbkdf2_sha256

    with session_factory() as session:
        session.add(
            User(
                email="legacy@x.com",
                hashed_password=pbkdf2_sha256.hash(PASSWORD),
                role="user",
                is_active=True,
            )
        )
        session.commit()
    assert client.post(
        f"{API}/auth/login", json={"email": "legacy@x.com", "password": "Wrong123!"}
    ).status_code == 401
    _login(client, "legacy@x.com")
    with session_factory() as session:
        upgraded = session.query(User).filter_by(email="legacy@x.com").one().hashed_password
    assert upgraded.startswith("$argon2id$")
    _login(client, "legacy@x.com")  # still works with the new hash


def test_unknown_email_and_wrong_password_look_identical(client, roles) -> None:
    unknown = client.post(f"{API}/auth/login", json={"email": "no@x.com", "password": PASSWORD})
    wrong = client.post(f"{API}/auth/login", json={"email": "user@x.com", "password": "Nope123!"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_first_registrant_is_not_super_admin_when_bootstrap_disabled(
    make_settings, session_factory
) -> None:
    app = create_app(make_settings(AUTH_BOOTSTRAP_VIA_REGISTRATION=False, RATE_LIMIT_ENABLED=False))
    app.dependency_overrides[get_db] = lambda: session_factory()
    with TestClient(app) as c:
        r = c.post(f"{API}/auth/register", json={"email": "first@x.com", "password": PASSWORD})
    assert r.status_code == 201
    assert r.json()["role"] == "user"


def test_me_permissions_reflect_role(client, roles) -> None:
    for name, role in (("user", "user"), ("admin", "admin"), ("super", "super_admin")):
        body = client.get(f"{API}/auth/me/permissions", headers=h(roles[name])).json()
        assert body["role"] == role
        assert set(body["permissions"]) == {p.value for p in permissions_for(role)}


# --- unauthenticated access ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/employees"),
        ("GET", "/employees/stats"),
        ("GET", f"/employees/{uuid.uuid4()}"),
        ("POST", "/employees"),
        ("PATCH", f"/employees/{uuid.uuid4()}"),
        ("DELETE", f"/employees/{uuid.uuid4()}"),
        ("GET", "/audit-logs"),
        ("GET", "/settings"),
        ("PATCH", "/settings"),
        ("GET", "/auth/users"),
        ("DELETE", f"/auth/users/{uuid.uuid4()}"),
        ("GET", "/auth/me/permissions"),
        # Previously reachable without any token:
        ("GET", "/deployments"),
        ("GET", f"/deployments/{uuid.uuid4()}"),
        ("GET", "/drift/overview"),
        ("GET", "/drift/alerts"),
        ("GET", f"/drift/models/{uuid.uuid4()}/reports"),
        ("GET", f"/drift/models/{uuid.uuid4()}/alerts"),
        ("POST", "/datasets/validate"),
    ],
)
def test_protected_endpoints_reject_anonymous_requests(client, method, path) -> None:
    response = client.request(method, f"{API}{path}", json={})
    assert response.status_code == 401, (method, path, response.text)


def test_public_endpoints_stay_public(client) -> None:
    assert client.get("/health").status_code == 200
    assert client.get(f"{API}/health").status_code == 200
    assert client.get(f"{API}/auth/registration-status").json() == {
        "allow_self_registration": True
    }


# --- employees: role matrix ---------------------------------------------------------------


def test_every_role_can_read_employees(client, roles, employee) -> None:
    for name in ("user", "admin", "super"):
        listing = client.get(f"{API}/employees", headers=h(roles[name]))
        assert listing.status_code == 200
        assert listing.json()["total"] == 1
        detail = client.get(f"{API}/employees/{employee['id']}", headers=h(roles[name]))
        assert detail.status_code == 200
        assert client.get(f"{API}/employees/stats", headers=h(roles[name])).status_code == 200


def test_user_never_receives_sensitive_employee_fields(client, roles, employee) -> None:
    listing = client.get(f"{API}/employees", headers=h(roles["user"])).json()
    assert listing["sensitive_fields_included"] is False
    for record in (listing["items"][0], client.get(
        f"{API}/employees/{employee['id']}", headers=h(roles["user"])
    ).json()):
        assert "salary" not in record and "phone" not in record
        assert "85000" not in str(record)
    admin_view = client.get(f"{API}/employees/{employee['id']}", headers=h(roles["admin"])).json()
    assert admin_view["salary"] == "85000.00"
    assert admin_view["phone"] == "+44 20 7946 0000"


def test_user_cannot_create_update_or_delete_employees(client, roles, employee) -> None:
    user = h(roles["user"])
    create = client.post(f"{API}/employees", json={**EMPLOYEE, "employee_code": "x2",
                                                   "email": "x2@x.com"}, headers=user)
    update = client.patch(f"{API}/employees/{employee['id']}", json={"job_title": "CEO"},
                          headers=user)
    delete = client.delete(f"{API}/employees/{employee['id']}", headers=user)
    for response in (create, update, delete):
        assert response.status_code == 403
        assert code(response) == "permission_denied"
    unchanged = client.get(f"{API}/employees/{employee['id']}", headers=user).json()
    assert unchanged["job_title"] == "Analyst"


def test_admin_creates_and_updates_any_employee_but_cannot_delete(client, roles, employee) -> None:
    assert employee["employee_code"] == "EMP-001"
    assert employee["email"] == "ada@example.com"  # normalised
    # admin2 did not create the record and may still edit it ("any employee").
    r = client.patch(
        f"{API}/employees/{employee['id']}",
        json={"job_title": "Lead Analyst", "salary": "90000.00", "employment_status": "on_leave"},
        headers=h(roles["admin2"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["job_title"] == "Lead Analyst"
    assert r.json()["updated_by_id"] == roles["admin2"]["user"]["id"]

    denied = client.delete(f"{API}/employees/{employee['id']}", headers=h(roles["admin"]))
    assert denied.status_code == 403


def test_super_admin_deletes_employee_and_reports_are_detached(client, roles, employee) -> None:
    report = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "employee_code": "emp-002", "email": "r@x.com",
              "manager_id": employee["id"]},
        headers=h(roles["admin"]),
    ).json()
    assert client.delete(
        f"{API}/employees/{employee['id']}", headers=h(roles["super"])
    ).status_code == 204
    assert client.get(
        f"{API}/employees/{employee['id']}", headers=h(roles["super"])
    ).status_code == 404
    survivor = client.get(f"{API}/employees/{report['id']}", headers=h(roles["super"])).json()
    assert survivor["manager_id"] is None


def test_employee_list_filters_search_and_pagination(client, roles) -> None:
    admin = h(roles["admin"])
    for i, (dept, status) in enumerate(
        [("Engineering", "active"), ("Engineering", "on_leave"), ("Sales", "active")]
    ):
        r = client.post(
            f"{API}/employees",
            json={**EMPLOYEE, "employee_code": f"E{i}", "email": f"e{i}@x.com",
                  "last_name": f"Name{i}", "department": dept, "employment_status": status},
            headers=admin,
        )
        assert r.status_code == 201, r.text

    def total(**params):
        return client.get(f"{API}/employees", params=params, headers=admin).json()["total"]

    assert total() == 3
    assert total(department="engineering") == 2
    assert total(employment_status="on_leave") == 1
    assert total(search="name2") == 1
    assert total(search="%") == 0  # LIKE wildcards are escaped
    page = client.get(f"{API}/employees", params={"limit": 2, "offset": 2}, headers=admin).json()
    assert len(page["items"]) == 1 and page["total"] == 3
    stats = client.get(f"{API}/employees/stats", headers=admin).json()
    assert stats == {"total": 3, "by_status": {"active": 2, "on_leave": 1},
                     "by_department": {"Engineering": 2, "Sales": 1}}


# --- employees: validation and integrity ----------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"salary": "-1"}, 422),
        ({"email": "not-an-email"}, 422),
        ({"employee_code": "bad code!"}, 422),
        ({"employment_status": "fired"}, 422),
        ({"hire_date": "1800-01-01"}, 422),
        ({"phone": "call me"}, 422),
        ({"first_name": "   "}, 422),
        ({"manager_id": str(uuid.uuid4())}, 422),  # manager must exist
    ],
)
def test_employee_validation(client, roles, overrides, status) -> None:
    r = client.post(f"{API}/employees", json={**EMPLOYEE, **overrides}, headers=h(roles["admin"]))
    assert r.status_code == status, r.text


@pytest.mark.parametrize(
    "extra",
    [{"id": str(uuid.uuid4())}, {"created_by_id": str(uuid.uuid4())}, {"role": "super_admin"}],
)
def test_employee_mass_assignment_is_rejected(client, roles, employee, extra) -> None:
    admin = h(roles["admin"])
    create = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "employee_code": "e9", "email": "e9@x.com", **extra},
        headers=admin,
    )
    assert create.status_code == 422
    update = client.patch(f"{API}/employees/{employee['id']}", json=extra, headers=admin)
    assert update.status_code == 422
    # employee_code is immutable after creation.
    immutable = client.patch(
        f"{API}/employees/{employee['id']}", json={"employee_code": "NEW"}, headers=admin
    )
    assert immutable.status_code == 422


def test_duplicate_employee_code_or_email_conflicts(client, roles, employee) -> None:
    admin = h(roles["admin"])
    same_code = client.post(
        f"{API}/employees", json={**EMPLOYEE, "email": "other@x.com"}, headers=admin
    )
    same_email = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "employee_code": "other", "email": "ADA@example.com"},
        headers=admin,
    )
    assert same_code.status_code == same_email.status_code == 409
    second = client.post(
        f"{API}/employees", json={**EMPLOYEE, "employee_code": "e2", "email": "b@x.com"},
        headers=admin,
    ).json()
    taken = client.patch(
        f"{API}/employees/{second['id']}", json={"email": "ada@example.com"}, headers=admin
    )
    assert taken.status_code == 409


def test_required_fields_cannot_be_nulled_but_optional_ones_can(client, roles, employee) -> None:
    admin = h(roles["admin"])
    url = f"{API}/employees/{employee['id']}"
    assert client.patch(url, json={"last_name": None}, headers=admin).status_code == 422
    cleared = client.patch(url, json={"phone": None, "salary": None}, headers=admin)
    assert cleared.status_code == 200
    assert cleared.json()["phone"] is None and cleared.json()["salary"] is None


def test_manager_cycles_are_rejected(client, roles, employee) -> None:
    admin = h(roles["admin"])
    b = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "employee_code": "b", "email": "b@x.com", "manager_id": employee["id"]},
        headers=admin,
    ).json()
    c = client.post(
        f"{API}/employees",
        json={**EMPLOYEE, "employee_code": "c", "email": "c@x.com", "manager_id": b["id"]},
        headers=admin,
    ).json()
    url = f"{API}/employees/{employee['id']}"
    assert client.patch(url, json={"manager_id": c["id"]}, headers=admin).status_code == 422
    assert client.patch(url, json={"manager_id": employee["id"]}, headers=admin).status_code == 422


# --- account administration and privilege escalation ----------------------------------------


def test_self_registration_always_yields_user_role(client, roles) -> None:
    for role in ("admin", "super_admin"):
        r = client.post(
            f"{API}/auth/register",
            json={"email": f"{role}@evil.com", "password": PASSWORD, "role": role},
        )
        assert r.status_code == 403
    r = client.post(f"{API}/auth/register", json={"email": "plain@evil.com", "password": PASSWORD})
    assert r.json()["role"] == "user"


def test_admin_cannot_escalate_privileges(client, roles) -> None:
    admin, me = h(roles["admin"]), roles["admin"]["user"]["id"]
    # Promote self.
    r = client.patch(f"{API}/auth/users/{me}", json={"role": "super_admin"}, headers=admin)
    assert r.status_code == 403
    # Promote a user.
    user_id = roles["user"]["user"]["id"]
    r = client.patch(f"{API}/auth/users/{user_id}", json={"role": "admin"}, headers=admin)
    assert r.status_code == 403
    # Create an admin / super admin account.
    for role in ("admin", "super_admin"):
        r = client.post(
            f"{API}/auth/register",
            json={"email": f"made-{role}@x.com", "password": PASSWORD, "role": role},
            headers=admin,
        )
        assert r.status_code == 403
    # Act on peers or super admins.
    for target in ("admin2", "super"):
        tid = roles[target]["user"]["id"]
        assert client.patch(
            f"{API}/auth/users/{tid}", json={"is_active": False}, headers=admin
        ).status_code == 403
        assert client.delete(f"{API}/auth/users/{tid}", headers=admin).status_code == 403
    me_now = client.get(f"{API}/auth/me", headers=admin).json()
    assert me_now["role"] == "admin"


def test_admin_manages_user_accounts_only(client, roles) -> None:
    admin, uid = h(roles["admin"]), roles["user"]["user"]["id"]
    r = client.patch(
        f"{API}/auth/users/{uid}", json={"is_active": False, "full_name": "Renamed"}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False
    # The deactivated user's existing access token stops working immediately.
    assert client.get(f"{API}/auth/me", headers=h(roles["user"])).status_code == 401
    # Admins may create plain user accounts.
    created = client.post(
        f"{API}/auth/register", json={"email": "new@x.com", "password": PASSWORD}, headers=admin
    )
    assert created.status_code == 201 and created.json()["role"] == "user"
    # But cannot delete accounts at all.
    assert client.delete(f"{API}/auth/users/{uid}", headers=admin).status_code == 403


def test_user_cannot_administer_anyone(client, roles) -> None:
    user = h(roles["user"])
    me = roles["user"]["user"]["id"]
    assert client.get(f"{API}/auth/users", headers=user).status_code == 403
    for payload in ({"role": "super_admin"}, {"role": "admin"}, {"is_active": True}):
        assert client.patch(f"{API}/auth/users/{me}", json=payload, headers=user).status_code == 403
    assert client.get(f"{API}/auth/me", headers=user).json()["role"] == "user"


def test_role_field_injection_is_rejected_everywhere(client, roles) -> None:
    user = h(roles["user"])
    # Unknown fields are refused rather than silently ignored.
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Another123!", "role": "super_admin"},
        headers=user,
    )
    assert r.status_code == 422
    r = client.post(
        f"{API}/auth/login",
        json={"email": "user@x.com", "password": PASSWORD, "role": "super_admin"},
    )
    assert r.status_code == 422


def test_role_claim_in_token_is_never_trusted(client, roles, rbac_settings) -> None:
    """A token claiming super_admin for a 'user' account grants nothing extra."""
    forged = security.create_access_token(
        {"sub": roles["user"]["user"]["id"], "role": "super_admin", "ver": 0}, rbac_settings
    )
    headers = {"Authorization": f"Bearer {forged}"}
    assert client.get(f"{API}/auth/me", headers=headers).json()["role"] == "user"
    assert client.get(f"{API}/auth/users", headers=headers).status_code == 403
    assert client.patch(
        f"{API}/settings", json={"maintenance_mode": True}, headers=headers
    ).status_code == 403


def test_tokens_with_wrong_type_or_signature_are_rejected(client, roles, rbac_settings) -> None:
    uid = roles["super"]["user"]["id"]
    not_access = security.create_access_token({"sub": uid, "ver": 0}, rbac_settings)
    payload = security.decode_access_token(not_access, rbac_settings)
    import jwt

    refresh_like = jwt.encode(
        {**payload, "type": "refresh"},
        rbac_settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )
    other_key = jwt.encode(payload, "a-completely-different-secret-key-0123456789", "HS256")
    expired = security.create_access_token(
        {"sub": uid, "ver": 0}, rbac_settings, expires_delta=timedelta(seconds=-5)
    )
    for token in (refresh_like, other_key, expired):
        r = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


def test_role_change_takes_effect_immediately_and_ends_sessions(client, roles) -> None:
    super_h, uid = h(roles["super"]), roles["user"]["user"]["id"]
    r = client.patch(f"{API}/auth/users/{uid}", json={"role": "admin"}, headers=super_h)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    # Old access and refresh tokens are dead; a fresh login carries the new role.
    assert client.get(f"{API}/auth/me", headers=h(roles["user"])).status_code == 401
    assert client.post(
        f"{API}/auth/refresh", json={"refresh_token": roles["user"]["refresh_token"]}
    ).status_code == 401
    fresh = _login(client, "user@x.com")
    assert fresh["user"]["role"] == "admin"
    assert client.post(
        f"{API}/employees", json=EMPLOYEE, headers=h(fresh)
    ).status_code == 201


def test_password_change_invalidates_existing_access_tokens(client, roles) -> None:
    old = roles["admin"]
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Changed123!"},
        headers=h(old),
    )
    assert r.status_code == 200
    assert client.get(f"{API}/auth/me", headers=h(old)).status_code == 401
    assert client.get(f"{API}/auth/me", headers=h(_login(client, "admin@x.com", "Changed123!"))
                      ).status_code == 200


def test_super_admin_role_management_and_deletion(client, roles, session_factory) -> None:
    super_h = h(roles["super"])
    uid = roles["user"]["user"]["id"]
    assert client.patch(
        f"{API}/auth/users/{uid}", json={"role": "super_admin"}, headers=super_h
    ).status_code == 200
    assert client.patch(
        f"{API}/auth/users/{uid}", json={"role": "user"}, headers=super_h
    ).status_code == 200
    # Super admins can manage other super admins (there are two active ones).
    s2 = roles["super2"]["user"]["id"]
    assert client.patch(
        f"{API}/auth/users/{s2}", json={"is_active": False}, headers=super_h
    ).status_code == 200
    # Delete: never yourself.
    me = roles["super"]["user"]["id"]
    assert client.delete(f"{API}/auth/users/{me}", headers=super_h).status_code == 403
    assert client.delete(f"{API}/auth/users/{uid}", headers=super_h).status_code == 204
    assert client.delete(f"{API}/auth/users/{uid}", headers=super_h).status_code == 404
    with session_factory() as session:
        entry = session.query(AuditLog).filter_by(action="user.delete").one()
    assert entry.details["email"] == "user@x.com"  # snapshot survives the deletion


def test_last_active_super_admin_is_protected(client, roles, session_factory) -> None:
    """Defence in depth: even a caller that bypasses the self-checks (e.g. a script acting
    on behalf of another account) cannot demote, deactivate or delete the last one."""
    from app.core.exceptions import DataValidationError
    from app.schemas.auth import UserUpdateRequest
    from app.services import auth_service

    super_h = h(roles["super"])
    s2 = roles["super2"]["user"]["id"]
    assert client.patch(
        f"{API}/auth/users/{s2}", json={"role": "admin"}, headers=super_h
    ).status_code == 200
    with session_factory() as session:
        last_id = uuid.UUID(roles["super"]["user"]["id"])
        # An actor object that is a super admin but not an *active stored* one.
        ghost = User(id=uuid.uuid4(), email="ghost@x.com", role="super_admin", is_active=True)
        for request in (UserUpdateRequest(is_active=False), UserUpdateRequest(role="admin")):
            with pytest.raises(DataValidationError, match="last active super admin"):
                auth_service.update_user(session, ghost, last_id, request)
            session.rollback()
        with pytest.raises(DataValidationError, match="last active super admin"):
            auth_service.delete_user(session, ghost, last_id)


def test_registration_cannot_target_unknown_roles(client, roles) -> None:
    for role in ("viewer", "ml_engineer", "root"):
        r = client.post(
            f"{API}/auth/register",
            json={"email": f"{role}@x.com", "password": PASSWORD, "role": role},
            headers=h(roles["super"]),
        )
        assert r.status_code == 422


# --- ML resources: role matrix -----------------------------------------------------------


def test_user_is_read_only_on_ml_resources(client, roles) -> None:
    from app.ml.synthetic import make_classification_frame
    from tests.helpers import to_csv_bytes

    user, admin = h(roles["user"]), h(roles["admin"])
    csv = to_csv_bytes(make_classification_frame(80))
    assert client.post(f"{API}/datasets", files={"file": ("d.csv", csv)}, headers=user
                       ).status_code == 403
    assert client.post(f"{API}/datasets/validate", files={"file": ("d.csv", csv)}, headers=user
                       ).status_code == 403
    uploaded = client.post(f"{API}/datasets", files={"file": ("d.csv", csv)}, headers=admin)
    assert uploaded.status_code == 201
    ds = uploaded.json()["dataset"]["id"]
    train = {"dataset_id": ds, "target_column": "label"}
    assert client.post(f"{API}/models/train", json=train, headers=user).status_code == 403
    model = client.post(f"{API}/models/train", json=train, headers=admin)
    assert model.status_code == 201
    # Reads are allowed.
    assert client.get(f"{API}/datasets", headers=user).status_code == 200
    assert client.get(f"{API}/deployments", headers=user).status_code == 200
    assert client.get(f"{API}/drift/overview", headers=user).status_code == 200
    assert client.get(f"{API}/monitoring/overview", headers=user).status_code == 200
    # Writes of every kind are refused.
    mid = model.json()["id"]
    for method, path, body in [
        ("POST", f"/models/{mid}/predict", {"records": [{"num_a": 1}]}),
        ("POST", f"/models/{mid}/deploy", {"environment": "production"}),
        ("POST", "/jobs", {"job_type": "batch_prediction", "model_id": mid,
                           "input_config": {"records": []}}),
        ("POST", "/llm/chat", {"messages": [{"role": "user", "content": "x"}]}),
        ("POST", "/experiments", {"name": "e", "dataset_id": ds, "target_column": "label"}),
    ]:
        r = client.request(method, f"{API}{path}", json=body, headers=user)
        assert r.status_code == 403, (path, r.text)
    # Deployment is reserved to super admins.
    assert client.post(f"{API}/models/{mid}/deploy", json={"environment": "production"},
                       headers=admin).status_code == 403
    assert client.post(f"{API}/models/{mid}/deploy", json={"environment": "production"},
                       headers=h(roles["super"])).status_code == 200


# --- audit log --------------------------------------------------------------------------------


def test_sensitive_operations_are_audited(client, roles, employee, session_factory) -> None:
    client.patch(
        f"{API}/employees/{employee['id']}", json={"salary": "1.00"}, headers=h(roles["admin"])
    )
    client.patch(
        f"{API}/auth/users/{roles['user']['user']['id']}", json={"role": "admin"},
        headers=h(roles["super"]),
    )
    client.post(f"{API}/auth/login", json={"email": "user@x.com", "password": "Bad12345!"})
    with session_factory() as session:
        actions = [a for (a,) in session.query(AuditLog.action).all()]
        update = session.query(AuditLog).filter_by(action="employee.update").one()
        failed = (
            session.query(AuditLog).filter_by(action="auth.login", outcome="failure").one()
        )
    for expected in ("user.bootstrap", "user.create", "auth.login", "employee.create",
                     "employee.update", "user.update"):
        assert expected in actions
    assert update.details["changes"]["salary"] == "changed"  # value never written
    assert update.actor_role == "admin"
    assert failed.details == {"reason": "bad_password"}
    for entry_text in (str(update.details), str(failed.details)):
        assert PASSWORD not in entry_text and "Bad12345!" not in entry_text


def test_audit_log_visibility_per_role(client, roles, employee) -> None:
    assert client.get(f"{API}/audit-logs", headers=h(roles["user"])).status_code == 403
    admin_view = client.get(f"{API}/audit-logs", headers=h(roles["admin"])).json()
    assert admin_view["total"] >= 1
    assert {e["category"] for e in admin_view["items"]} <= {"employee", "ml"}
    # Admins cannot widen their scope with a filter.
    sneaky = client.get(
        f"{API}/audit-logs", params={"category": "auth"}, headers=h(roles["admin"])
    ).json()
    assert sneaky["total"] == 0
    super_view = client.get(f"{API}/audit-logs", headers=h(roles["super"])).json()
    assert {"auth", "user_admin", "employee"} <= {e["category"] for e in super_view["items"]}
    assert super_view["total"] > admin_view["total"]


# --- settings and maintenance mode ---------------------------------------------------------


def test_only_super_admin_changes_settings(client, roles) -> None:
    for name in ("user", "admin"):
        r = client.patch(
            f"{API}/settings", json={"announcement_banner": "hi"}, headers=h(roles[name])
        )
        assert r.status_code == 403
    r = client.patch(
        f"{API}/settings", json={"announcement_banner": "  Hello  "}, headers=h(roles["super"])
    )
    assert r.status_code == 200
    assert r.json()["announcement_banner"] == "Hello"
    assert client.get(f"{API}/settings", headers=h(roles["user"])).json()[
        "announcement_banner"
    ] == "Hello"


@pytest.mark.parametrize(
    "payload",
    [{"maintenance_mode": "true"}, {"maintenance_mode": 1}, {"unknown": True},
     {"announcement_banner": "x" * 501}],
)
def test_settings_are_strictly_typed(client, roles, payload) -> None:
    r = client.patch(f"{API}/settings", json=payload, headers=h(roles["super"]))
    assert r.status_code == 422


def test_disabling_self_registration(client, roles) -> None:
    assert client.patch(
        f"{API}/settings", json={"allow_self_registration": False}, headers=h(roles["super"])
    ).status_code == 200
    assert client.get(f"{API}/auth/registration-status").json() == {
        "allow_self_registration": False
    }
    blocked = client.post(f"{API}/auth/register", json={"email": "z@x.com", "password": PASSWORD})
    assert blocked.status_code == 403
    # Administrators can still provision accounts.
    assert client.post(
        f"{API}/auth/register", json={"email": "z@x.com", "password": PASSWORD},
        headers=h(roles["admin"]),
    ).status_code == 201


def test_maintenance_mode_blocks_writes_except_super_admin(client, roles, employee) -> None:
    assert client.patch(
        f"{API}/settings", json={"maintenance_mode": True}, headers=h(roles["super"])
    ).status_code == 200
    url = f"{API}/employees/{employee['id']}"
    blocked = client.patch(url, json={"job_title": "X"}, headers=h(roles["admin"]))
    assert blocked.status_code == 503
    assert code(blocked) == "maintenance_mode"
    # Reads still work for everyone; super admins can still write (and turn it off).
    assert client.get(url, headers=h(roles["user"])).status_code == 200
    assert client.patch(url, json={"job_title": "Y"}, headers=h(roles["super"])).status_code == 200
    assert client.patch(
        f"{API}/settings", json={"maintenance_mode": False}, headers=h(roles["super"])
    ).status_code == 200
    assert client.patch(url, json={"job_title": "Z"}, headers=h(roles["admin"])).status_code == 200


# --- metrics token ------------------------------------------------------------------------


def test_metrics_token_when_configured(make_settings, session_factory) -> None:
    app = create_app(make_settings(METRICS_AUTH_TOKEN="scrape-secret-0123456789"))
    app.dependency_overrides[get_db] = lambda: session_factory()
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/metrics").status_code == 401
        assert c.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = c.get("/metrics", headers={"Authorization": "Bearer scrape-secret-0123456789"})
        assert ok.status_code == 200
