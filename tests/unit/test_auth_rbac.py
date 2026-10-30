import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def test_auth_registration_and_login(api_client: TestClient) -> None:
    # 1. First registered user automatically becomes admin
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
    assert data["role"] == "admin"
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
    assert tokens["user"]["role"] == "admin"

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


def test_rbac_permissions_and_last_admin_protection(api_client: TestClient) -> None:
    # Register Admin
    api_client.post(
        f"{API}/auth/register",
        json={"email": "admin2@example.com", "password": "Password123!", "full_name": "Admin 2"},
    )
    admin_login = api_client.post(
        f"{API}/auth/login",
        json={"email": "admin2@example.com", "password": "Password123!"},
    ).json()
    admin_token = admin_login["access_token"]
    admin_id = admin_login["user"]["id"]

    # Register ML Engineer
    api_client.post(
        f"{API}/auth/register",
        json={
            "email": "mle@example.com",
            "password": "Password123!",
            "full_name": "ML Engineer",
            "role": "ml_engineer",
        },
    )
    mle_login = api_client.post(
        f"{API}/auth/login",
        json={"email": "mle@example.com", "password": "Password123!"},
    ).json()
    mle_token = mle_login["access_token"]

    # Register Viewer
    api_client.post(
        f"{API}/auth/register",
        json={
            "email": "viewer@example.com",
            "password": "Password123!",
            "full_name": "Viewer",
            "role": "viewer",
        },
    )
    viewer_login = api_client.post(
        f"{API}/auth/login",
        json={"email": "viewer@example.com", "password": "Password123!"},
    ).json()
    viewer_token = viewer_login["access_token"]

    # Test 1: Only admin can access user list
    res_viewer_users = api_client.get(
        f"{API}/auth/users",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_viewer_users.status_code == 403

    res_admin_users = api_client.get(
        f"{API}/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_users.status_code == 200
    assert len(res_admin_users.json()["items"]) >= 3

    # Test 2: Deployment endpoint requires admin (MLE is 403)
    fake_model_id = "00000000-0000-0000-0000-000000000001"
    deploy_mle = api_client.post(
        f"{API}/models/{fake_model_id}/deploy",
        json={"environment": "production"},
        headers={"Authorization": f"Bearer {mle_token}"},
    )
    assert deploy_mle.status_code == 403

    # Deploy viewer is 403
    deploy_viewer = api_client.post(
        f"{API}/models/{fake_model_id}/deploy",
        json={"environment": "production"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert deploy_viewer.status_code == 403

    # Test 3: Last active admin protection
    demote_res = api_client.patch(
        f"{API}/auth/users/{admin_id}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert demote_res.status_code == 400
    assert "last active administrator" in demote_res.text.lower()
