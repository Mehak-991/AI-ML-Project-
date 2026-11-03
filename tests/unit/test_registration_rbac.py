"""Registration and role assignment through the real auth stack (no mocked users)."""

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import create_app

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd"


@pytest.fixture
def client(make_settings, session_factory):
    app = create_app(make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False))

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _register(client, email: str, headers: dict | None = None, **fields):
    body = {"email": email, "password": PASSWORD, **fields}
    return client.post(f"{API}/auth/register", json=body, headers=headers or {})


def _bearer(client, email: str) -> dict:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _role_of(client, headers: dict, email: str) -> str:
    users = client.get(f"{API}/auth/users", headers=headers).json()["items"]
    return next(u["role"] for u in users if u["email"] == email)


@pytest.fixture
def admin(client) -> dict:
    assert _register(client, "root@x.com").json()["role"] == "admin"
    return _bearer(client, "root@x.com")


def test_first_user_receives_administrator(client) -> None:
    response = _register(client, "first@x.com")
    assert response.status_code == 201
    assert response.json()["role"] == "admin"


def test_subsequent_public_registrations_receive_viewer(client, admin) -> None:
    for email in ("two@x.com", "three@x.com"):
        response = _register(client, email)
        assert response.status_code == 201
        assert response.json()["role"] == "viewer"


@pytest.mark.parametrize("role", ["admin", "ml_engineer"])
def test_public_registration_cannot_assign_elevated_roles(client, admin, role) -> None:
    response = _register(client, "attacker@x.com", role=role)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert (
        client.post(
            f"{API}/auth/login", json={"email": "attacker@x.com", "password": PASSWORD}
        ).status_code
        == 401
    ), "a rejected registration must not leave an account behind"


@pytest.mark.parametrize("role", ["superuser", "ADMIN", "", None])
def test_unknown_role_values_are_rejected(client, admin, role) -> None:
    assert _register(client, "odd@x.com", role=role).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [{"is_active": True}, {"is_admin": True}, {"hashed_password": "x"}, {"id": "1"}],
)
def test_registration_rejects_extra_payload_fields(client, admin, extra) -> None:
    assert _register(client, "extra@x.com", **extra).status_code == 422


def test_invalid_token_gets_no_elevated_rights(client, admin) -> None:
    forged = {"Authorization": "Bearer not.a.token"}
    assert _register(client, "forged@x.com", headers=forged, role="admin").status_code == 403


@pytest.mark.parametrize("creator_role", ["viewer", "ml_engineer"])
def test_non_admins_cannot_create_elevated_accounts(client, admin, creator_role) -> None:
    assert _register(client, "creator@x.com", headers=admin, role=creator_role).status_code == 201
    creator = _bearer(client, "creator@x.com")
    for role in ("admin", "ml_engineer"):
        assert _register(client, f"{role}@x.com", headers=creator, role=role).status_code == 403


@pytest.mark.parametrize("role", ["admin", "ml_engineer", "viewer"])
def test_administrator_can_create_users_with_any_role(client, admin, role) -> None:
    response = _register(client, "new@x.com", headers=admin, role=role)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == role
    assert client.get(f"{API}/auth/me", headers=_bearer(client, "new@x.com")).json()["role"] == role


def test_administrator_can_promote_users(client, admin) -> None:
    user_id = _register(client, "user@x.com").json()["id"]
    token = _bearer(client, "user@x.com")
    denied = client.get(f"{API}/auth/users", headers=token)
    assert denied.status_code == 403

    promoted = client.patch(
        f"{API}/auth/users/{user_id}", json={"role": "admin"}, headers=admin
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    # Roles are read from the database per request, so the existing token gains access at once.
    assert client.get(f"{API}/auth/users", headers=token).status_code == 200


@pytest.mark.parametrize("actor_role", ["viewer", "ml_engineer"])
def test_non_admins_cannot_promote_anyone_including_themselves(client, admin, actor_role) -> None:
    actor_id = _register(client, "actor@x.com", headers=admin, role=actor_role).json()["id"]
    other_id = _register(client, "other@x.com").json()["id"]
    actor = _bearer(client, "actor@x.com")
    for target in (actor_id, other_id):
        response = client.patch(
            f"{API}/auth/users/{target}", json={"role": "admin"}, headers=actor
        )
        assert response.status_code == 403
    assert _role_of(client, admin, "actor@x.com") == actor_role
    assert _role_of(client, admin, "other@x.com") == "viewer"


def test_promotion_requires_authentication(client, admin) -> None:
    user_id = _register(client, "anon@x.com").json()["id"]
    response = client.patch(f"{API}/auth/users/{user_id}", json={"role": "admin"})
    assert response.status_code == 401
    assert _role_of(client, admin, "anon@x.com") == "viewer"


def test_bootstrap_does_not_reopen_while_any_account_exists(client, admin) -> None:
    """Deactivating the only admin must not let the next registrant become admin."""
    other_admin = _register(client, "second@x.com", headers=admin, role="admin").json()
    first = next(
        u
        for u in client.get(f"{API}/auth/users", headers=admin).json()["items"]
        if u["email"] == "root@x.com"
    )
    second = _bearer(client, "second@x.com")
    assert (
        client.patch(
            f"{API}/auth/users/{first['id']}", json={"is_active": False}, headers=second
        ).status_code
        == 200
    )
    client.patch(f"{API}/auth/users/{other_admin['id']}", json={"role": "viewer"}, headers=second)
    assert _register(client, "late@x.com").json()["role"] == "viewer"


def test_logging_in_never_changes_a_role(client, admin) -> None:
    _register(client, "stay@x.com")
    for _ in range(2):
        _bearer(client, "stay@x.com")
    assert _role_of(client, admin, "stay@x.com") == "viewer"
    assert _role_of(client, admin, "root@x.com") == "admin"
