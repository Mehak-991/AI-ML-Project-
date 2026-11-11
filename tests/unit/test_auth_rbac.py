import pytest
from fastapi.testclient import TestClient

from tests.helpers import DEFAULT_TEST_PASSWORD, insert_account

API = "/api/v1"


def test_auth_registration_and_login(api_client: TestClient) -> None:
    # 1. Public registration always creates a read-only user, even the very first account.
    reg = api_client.post(
        f"{API}/auth/register",
        json={
            "email": "member@example.com",
            "password": "Password123!",
            "full_name": "Member User",
        },
    )
    assert reg.status_code == 201, reg.text
    data = reg.json()
    assert data["role"] == "user"
    assert data["email"] == "member@example.com"
    assert "password" not in data

    # 2. Duplicate registration rejected
    dup_res = api_client.post(
        f"{API}/auth/register",
        json={"email": "member@example.com", "password": "AnotherPassword123!", "full_name": "Duplicate"},
    )
    assert dup_res.status_code == 409

    # 3. Weak password rejected
    weak_res = api_client.post(
        f"{API}/auth/register",
        json={"email": "weak@example.com", "password": "123", "full_name": "Weak User"},
    )
    assert weak_res.status_code == 422

    # 4. Login with invalid password
    bad_login = api_client.post(
        f"{API}/auth/login", json={"email": "member@example.com", "password": "WrongPassword123!"}
    )
    assert bad_login.status_code == 401

    # 5. Login with valid password
    login_res = api_client.post(
        f"{API}/auth/login", json={"email": "member@example.com", "password": "Password123!"}
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert tokens["user"]["role"] == "user"

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 6. /auth/me profile, with the permissions computed on the server
    me_res = api_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_res.status_code == 200
    body = me_res.json()
    assert body["email"] == "member@example.com"
    assert "resources:read" in body["permissions"]
    assert "users:manage" not in body["permissions"]

    # 7. Refresh token rotation
    refresh_res = api_client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert new_tokens["access_token"] != access_token
    assert new_tokens["refresh_token"] != refresh_token

    # 8. Old refresh token should now be revoked / invalid
    old_refresh_res = api_client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert old_refresh_res.status_code == 401

    # 9. Logout
    logout_res = api_client.post(
        f"{API}/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout_res.status_code == 200


def _token(client: TestClient, email: str) -> dict:
    login = client.post(f"{API}/auth/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.fixture
def three_roles(api_client, session_factory):
    insert_account(session_factory, "root@example.com", "superadmin")
    insert_account(session_factory, "staff@example.com", "admin")
    insert_account(session_factory, "member@example.com", "user")
    return {
        "superadmin": _token(api_client, "root@example.com"),
        "admin": _token(api_client, "staff@example.com"),
        "user": _token(api_client, "member@example.com"),
    }


def test_rbac_permissions_and_last_superadmin_protection(api_client: TestClient, three_roles) -> None:
    # Only the superadmin can list users.
    assert api_client.get(f"{API}/auth/users", headers=three_roles["user"]).status_code == 403
    assert api_client.get(f"{API}/auth/users", headers=three_roles["admin"]).status_code == 403
    listed = api_client.get(f"{API}/auth/users", headers=three_roles["superadmin"])
    assert listed.status_code == 200
    assert len(listed.json()["items"]) >= 3

    # Deployment management: admin and superadmin pass authorization (404 = no such model);
    # a read-only user is refused.
    fake_model_id = "00000000-0000-0000-0000-000000000001"
    body = {"environment": "production"}
    deploy = lambda who: api_client.post(  # noqa: E731
        f"{API}/models/{fake_model_id}/deploy", json=body, headers=three_roles[who]
    )
    assert deploy("user").status_code == 403
    assert deploy("admin").status_code == 404
    assert deploy("superadmin").status_code == 404

    # The last active superadmin cannot be demoted or deactivated, even by themselves.
    users = {u["email"]: u["id"] for u in listed.json()["items"]}
    root_id = users["root@example.com"]
    revoke_self = api_client.delete(f"{API}/auth/users/{root_id}/superadmin", headers=three_roles["superadmin"])
    assert revoke_self.status_code == 403
    deactivate_self = api_client.patch(
        f"{API}/auth/users/{root_id}", json={"is_active": False}, headers=three_roles["superadmin"]
    )
    assert deactivate_self.status_code == 403
