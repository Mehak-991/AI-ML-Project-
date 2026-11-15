import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def test_auth_registration_and_login(api_client: TestClient) -> None:
    # 1. First registered user automatically becomes super_admin (bootstrap, non-production)
    reg_admin = api_client.post(
        f"{API}/auth/register",
        json={
            "email": "admin@example.com",
            "password": "Password123!",
            "full_name": "Admin User",
        },
    )
    assert reg_admin.status_code == 201, reg_admin.text
    data = reg_admin.json()
    assert data["role"] == "super_admin"
    assert data["email"] == "admin@example.com"
    assert "password" not in data

    # 2. Duplicate registration rejected
    dup_res = api_client.post(
        f"{API}/auth/register",
        json={
            "email": "admin@example.com",
            "password": "AnotherPassword123!",
            "full_name": "Duplicate User",
        },
    )
    assert dup_res.status_code == 409

    # 3. Weak password rejected
    weak_res = api_client.post(
        f"{API}/auth/register",
        json={
            "email": "weak@example.com",
            "password": "123",
            "full_name": "Weak User",
        },
    )
    assert weak_res.status_code == 422

    # 4. Login with invalid password
    bad_login = api_client.post(
        f"{API}/auth/login",
        json={"email": "admin@example.com", "password": "WrongPassword123!"},
    )
    assert bad_login.status_code == 401

    # 5. Login with valid password
    login_res = api_client.post(
        f"{API}/auth/login",
        json={"email": "admin@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert tokens["user"]["role"] == "super_admin"

    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # 6. /auth/me profile
    me_res = api_client.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "admin@example.com"

    # 7. Refresh token rotation
    refresh_res = api_client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert new_tokens["access_token"] != access_token
    assert new_tokens["refresh_token"] != refresh_token

    # 8. Old refresh token should now be revoked / invalid
    old_refresh_res = api_client.post(
        f"{API}/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert old_refresh_res.status_code == 401

    # 9. Logout
    logout_res = api_client.post(
        f"{API}/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
    )
    assert logout_res.status_code == 200


def _register_and_login(client: TestClient, email: str, role: str | None = None) -> dict:
    body = {"email": email, "password": "Password123!", "full_name": email.split("@")[0]}
    if role:
        body["role"] = role
    # api_client treats token-less calls as a mock super admin, so elevated roles are allowed.
    assert client.post(f"{API}/auth/register", json=body).status_code == 201
    return client.post(
        f"{API}/auth/login", json={"email": email, "password": "Password123!"}
    ).json()


def test_rbac_permissions_and_self_protection(api_client: TestClient) -> None:
    root = _register_and_login(api_client, "root@example.com")
    assert root["user"]["role"] == "super_admin"
    admin = _register_and_login(api_client, "admin@example.com", "admin")
    user = _register_and_login(api_client, "user@example.com", "user")
    auth = lambda t: {"Authorization": f"Bearer {t['access_token']}"}  # noqa: E731

    # User list: admin and super admin yes, user no.
    assert api_client.get(f"{API}/auth/users", headers=auth(user)).status_code == 403
    listing = api_client.get(f"{API}/auth/users", headers=auth(admin))
    assert listing.status_code == 200
    assert listing.json()["total"] >= 3

    # Deployment requires super_admin.
    fake_model_id = "00000000-0000-0000-0000-000000000001"
    for tokens in (admin, user):
        response = api_client.post(
            f"{API}/models/{fake_model_id}/deploy",
            json={"environment": "production"},
            headers=auth(tokens),
        )
        assert response.status_code == 403

    # Nobody can change their own role, not even the (only) super admin.
    demote_self = api_client.patch(
        f"{API}/auth/users/{root['user']['id']}", json={"role": "user"}, headers=auth(root)
    )
    assert demote_self.status_code == 403
    assert "own role" in demote_self.text
    deactivate_self = api_client.patch(
        f"{API}/auth/users/{root['user']['id']}", json={"is_active": False}, headers=auth(root)
    )
    assert deactivate_self.status_code == 403
