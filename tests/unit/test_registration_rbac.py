"""Registration and role assignment through the real auth stack (no mocked users)."""

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import create_app
from tests.helpers import DEFAULT_TEST_PASSWORD as PASSWORD
from tests.helpers import insert_account

API = "/api/v1"


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


def _create(client, headers: dict, email: str, role: str = "user"):
    return client.post(
        f"{API}/auth/users", json={"email": email, "password": PASSWORD, "role": role}, headers=headers
    )


@pytest.fixture
def superadmin(client, session_factory) -> dict:
    """A superadmin created out of band, as the server-side bootstrap would."""
    insert_account(session_factory, "root@x.com", "superadmin")
    return _bearer(client, "root@x.com")


def test_first_public_registration_is_only_a_user(client) -> None:
    response = _register(client, "first@x.com")
    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_every_public_registration_receives_user(client, superadmin) -> None:
    for email in ("two@x.com", "three@x.com"):
        response = _register(client, email)
        assert response.status_code == 201
        assert response.json()["role"] == "user"


@pytest.mark.parametrize("role", ["admin", "superadmin", "ml_engineer", "viewer", "user", "ADMIN", "", None])
def test_registration_has_no_role_field_at_all(client, superadmin, role) -> None:
    """Role assignment was removed from the public payload: any value, even a harmless one, is a
    validation error, and no account is left behind."""
    assert _register(client, "odd@x.com", role=role).status_code == 422
    assert (
        client.post(f"{API}/auth/login", json={"email": "odd@x.com", "password": PASSWORD}).status_code == 401
    )


@pytest.mark.parametrize(
    "extra",
    [{"is_active": True}, {"is_admin": True}, {"hashed_password": "x"}, {"id": "1"}, {"permissions": ["users:manage"]}],
)
def test_registration_rejects_extra_payload_fields(client, superadmin, extra) -> None:
    assert _register(client, "extra@x.com", **extra).status_code == 422


def test_invalid_token_gets_no_elevated_rights(client, superadmin) -> None:
    forged = {"Authorization": "Bearer not.a.token"}
    assert _register(client, "forged@x.com", headers=forged, role="admin").status_code == 422
    plain = _register(client, "forged2@x.com", headers=forged)
    assert plain.status_code == 201 and plain.json()["role"] == "user"


@pytest.mark.parametrize("creator_role", ["user", "admin"])
def test_only_a_superadmin_can_create_accounts(client, superadmin, session_factory, creator_role) -> None:
    insert_account(session_factory, "creator@x.com", creator_role)
    creator = _bearer(client, "creator@x.com")
    for role in ("user", "admin"):
        assert _create(client, creator, f"{role}@x.com", role).status_code == 403
    assert _role_of(client, superadmin, "creator@x.com") == creator_role


@pytest.mark.parametrize("role", ["admin", "user"])
def test_superadmin_can_create_users_with_user_or_admin_role(client, superadmin, role) -> None:
    response = _create(client, superadmin, "new@x.com", role)
    assert response.status_code == 201, response.text
    assert response.json()["role"] == role
    assert client.get(f"{API}/auth/me", headers=_bearer(client, "new@x.com")).json()["role"] == role


@pytest.mark.parametrize("role", ["superadmin", "ml_engineer", "viewer", "root"])
def test_account_creation_can_never_make_a_superadmin(client, superadmin, role) -> None:
    assert _create(client, superadmin, "nope@x.com", role).status_code == 422


def test_superadmin_can_promote_and_demote_between_user_and_admin(client, superadmin) -> None:
    user_id = _register(client, "user@x.com").json()["id"]
    token = _bearer(client, "user@x.com")
    # A plain user cannot even list users.
    assert client.get(f"{API}/auth/users", headers=token).status_code == 403

    promoted = client.patch(f"{API}/auth/users/{user_id}", json={"role": "admin"}, headers=superadmin)
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    # Roles are read from the database per request, so the existing token gains admin rights at
    # once (deployments: admin passes authorization, so the unknown model is a 404, not a 403).
    deploy = client.post(
        f"{API}/models/00000000-0000-0000-0000-000000000001/deploy",
        json={"environment": "production"},
        headers=token,
    )
    assert deploy.status_code == 404
    # Admin is still not a user administrator.
    assert client.get(f"{API}/auth/users", headers=token).status_code == 403

    demoted = client.patch(f"{API}/auth/users/{user_id}", json={"role": "user"}, headers=superadmin)
    assert demoted.status_code == 200 and demoted.json()["role"] == "user"
    assert client.post(
        f"{API}/models/00000000-0000-0000-0000-000000000001/deploy",
        json={"environment": "production"},
        headers=token,
    ).status_code == 403


@pytest.mark.parametrize("actor_role", ["user", "admin"])
def test_non_superadmins_cannot_change_any_role_including_their_own(
    client, superadmin, session_factory, actor_role
) -> None:
    actor = insert_account(session_factory, "actor@x.com", actor_role)
    other_id = _register(client, "other@x.com").json()["id"]
    token = _bearer(client, "actor@x.com")
    for target in (str(actor.id), other_id):
        for role in ("admin", "user", "superadmin"):
            response = client.patch(f"{API}/auth/users/{target}", json={"role": role}, headers=token)
            assert response.status_code in (403, 422)
            assert response.status_code != 200
        for suffix_call in (client.post, client.delete):
            assert suffix_call(f"{API}/auth/users/{target}/superadmin", headers=token).status_code == 403
    assert _role_of(client, superadmin, "actor@x.com") == actor_role
    assert _role_of(client, superadmin, "other@x.com") == "user"


def test_role_changes_require_authentication(client, superadmin) -> None:
    user_id = _register(client, "anon@x.com").json()["id"]
    assert client.patch(f"{API}/auth/users/{user_id}", json={"role": "admin"}).status_code == 401
    assert client.post(f"{API}/auth/users/{user_id}/superadmin").status_code == 401
    assert _role_of(client, superadmin, "anon@x.com") == "user"


def test_deactivating_every_privileged_account_never_lets_a_registrant_become_admin(
    client, superadmin, session_factory
) -> None:
    """Registration cannot create admins, whatever state the privileged accounts are in."""
    second = insert_account(session_factory, "second@x.com", "superadmin")
    second_token = _bearer(client, "second@x.com")
    first_id = next(
        u["id"] for u in client.get(f"{API}/auth/users", headers=superadmin).json()["items"] if u["email"] == "root@x.com"
    )
    assert client.patch(f"{API}/auth/users/{first_id}", json={"is_active": False}, headers=second_token).status_code == 200
    # The remaining superadmin cannot be removed either.
    assert client.patch(f"{API}/auth/users/{second.id}", json={"is_active": False}, headers=second_token).status_code == 403
    late = _register(client, "late@x.com")
    assert late.json()["role"] == "user"
