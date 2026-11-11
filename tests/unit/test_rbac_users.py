"""User administration under RBAC v2: roles, superadmin protection, deletion, audit trail."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.exceptions import ConflictError
from app.database.models.audit import AuditLog
from app.database.models.user import User
from app.database.session import get_db
from app.main import create_app
from app.schemas.auth import UserUpdateRequest
from app.services import audit_service, auth_service
from tests.helpers import DEFAULT_TEST_PASSWORD as PASSWORD
from tests.helpers import insert_account

API = "/api/v1"


@pytest.fixture
def make_client(make_settings, session_factory):
    def _make(**overrides):
        app = create_app(make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False, **overrides))

        def _get_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = _get_db
        return TestClient(app, raise_server_exceptions=False)

    return _make


@pytest.fixture
def client(make_client):
    with make_client() as c:
        yield c


def _login(client, email: str) -> dict:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def root(client, session_factory):
    insert_account(session_factory, "root@x.com", "superadmin")
    return _login(client, "root@x.com")


def _id_of(session_factory, email: str) -> str:
    with session_factory() as session:
        return str(session.scalar(select(User.id).where(User.email == email)))


def _audit(session_factory, action: str | None = None) -> list[AuditLog]:
    """Entries in insertion order. SQLite timestamps have one-second resolution, so entries made
    in the same second tie on created_at; rowid is the true order here."""
    with session_factory() as session:
        stmt = select(AuditLog).order_by(text("audit_logs.rowid"))
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return list(session.scalars(stmt).all())


# --- /auth/me ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "role", "has_users_manage"),
    [("user", "user", False), ("admin", "admin", False), ("superadmin", "superadmin", True)],
)
def test_me_returns_the_server_computed_permissions(client, session_factory, stored, role, has_users_manage) -> None:
    insert_account(session_factory, f"{stored}@x.com", stored)
    body = client.get(f"{API}/auth/me", headers=_login(client, f"{stored}@x.com")).json()
    assert body["role"] == role
    assert ("users:manage" in body["permissions"]) is has_users_manage
    assert body["permissions"] == sorted(body["permissions"])


def test_login_response_carries_the_same_permissions(client, session_factory) -> None:
    insert_account(session_factory, "admin@x.com", "admin")
    login = client.post(f"{API}/auth/login", json={"email": "admin@x.com", "password": PASSWORD}).json()
    assert "ml:operate" in login["user"]["permissions"]
    assert "users:manage" not in login["user"]["permissions"]


def test_profile_update_changes_only_the_display_name(client, session_factory) -> None:
    insert_account(session_factory, "me@x.com", "user", full_name="Before")
    headers = _login(client, "me@x.com")
    updated = client.patch(f"{API}/auth/me", json={"full_name": "After"}, headers=headers)
    assert updated.status_code == 200 and updated.json()["full_name"] == "After"
    assert updated.json()["role"] == "user"
    for field in ("role", "is_active", "permissions", "email"):
        r = client.patch(f"{API}/auth/me", json={"full_name": "x", field: "admin"}, headers=headers)
        assert r.status_code == 422, field


# --- creating and changing accounts ----------------------------------------------------------


def test_creation_and_role_changes_are_audited_with_before_and_after(client, root, session_factory) -> None:
    created = client.post(
        f"{API}/auth/users", json={"email": "new@x.com", "password": PASSWORD, "role": "user"}, headers=root
    )
    assert created.status_code == 201
    uid = created.json()["id"]
    assert client.patch(f"{API}/auth/users/{uid}", json={"role": "admin"}, headers=root).status_code == 200
    assert client.patch(f"{API}/auth/users/{uid}", json={"role": "user"}, headers=root).status_code == 200

    made = _audit(session_factory, audit_service.ACTION_USER_CREATED)
    assert len(made) == 1 and made[0].actor_email == "root@x.com" and made[0].target_email == "new@x.com"
    assert made[0].after["role"] == "user" and made[0].actor_role == "superadmin"

    changes = _audit(session_factory, audit_service.ACTION_ROLE_CHANGED)
    assert [(c.before["role"], c.after["role"]) for c in changes] == [("user", "admin"), ("admin", "user")]
    assert all(c.target_id and str(c.target_id) == uid for c in changes)


def test_setting_the_role_a_user_already_has_changes_nothing_and_writes_no_audit(client, root, session_factory) -> None:
    insert_account(session_factory, "same@x.com", "user")
    uid = _id_of(session_factory, "same@x.com")
    r = client.patch(f"{API}/auth/users/{uid}", json={"role": "user"}, headers=root)
    assert r.status_code == 200
    assert _audit(session_factory, audit_service.ACTION_ROLE_CHANGED) == []


def test_deactivation_and_reactivation_are_audited_and_end_sessions(client, root, session_factory) -> None:
    insert_account(session_factory, "off@x.com", "admin")
    victim = client.post(f"{API}/auth/login", json={"email": "off@x.com", "password": PASSWORD}).json()
    uid = victim["user"]["id"]
    assert client.patch(f"{API}/auth/users/{uid}", json={"is_active": False}, headers=root).status_code == 200
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": victim["refresh_token"]}).status_code == 401
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {victim['access_token']}"}).status_code == 401
    assert client.patch(f"{API}/auth/users/{uid}", json={"is_active": True}, headers=root).status_code == 200

    off = _audit(session_factory, audit_service.ACTION_DEACTIVATED)
    on = _audit(session_factory, audit_service.ACTION_REACTIVATED)
    assert len(off) == 1 and off[0].before == {"is_active": True} and off[0].after == {"is_active": False}
    assert len(on) == 1 and on[0].after == {"is_active": True}


def test_nobody_can_change_their_own_role_or_status(client, root, session_factory) -> None:
    uid = _id_of(session_factory, "root@x.com")
    for body in ({"role": "user"}, {"role": "admin"}, {"is_active": False}):
        assert client.patch(f"{API}/auth/users/{uid}", json=body, headers=root).status_code == 403
    assert client.delete(f"{API}/auth/users/{uid}/superadmin", headers=root).status_code == 403
    assert client.delete(f"{API}/auth/users/{uid}?confirm_email=root@x.com", headers=root).status_code == 403


def test_a_superadmin_cannot_be_changed_with_the_generic_role_update(client, root, session_factory) -> None:
    insert_account(session_factory, "second@x.com", "superadmin")
    uid = _id_of(session_factory, "second@x.com")
    r = client.patch(f"{API}/auth/users/{uid}", json={"role": "user"}, headers=root)
    assert r.status_code == 409 and "revoke superadmin" in r.text


# --- superadmin: grant, revoke, last-superadmin protection -----------------------------------


def test_grant_and_revoke_superadmin_are_audited(client, root, session_factory) -> None:
    insert_account(session_factory, "adm@x.com", "admin")
    uid = _id_of(session_factory, "adm@x.com")
    granted = client.post(f"{API}/auth/users/{uid}/superadmin", headers=root)
    assert granted.status_code == 200 and granted.json()["role"] == "superadmin"
    assert client.post(f"{API}/auth/users/{uid}/superadmin", headers=root).status_code == 409  # already one

    revoked = client.delete(f"{API}/auth/users/{uid}/superadmin", headers=root)
    assert revoked.status_code == 200 and revoked.json()["role"] == "admin"

    g = _audit(session_factory, audit_service.ACTION_SUPERADMIN_GRANTED)
    r = _audit(session_factory, audit_service.ACTION_SUPERADMIN_REVOKED)
    assert [(e.before["role"], e.after["role"]) for e in g] == [("admin", "superadmin")]
    assert [(e.before["role"], e.after["role"]) for e in r] == [("superadmin", "admin")]


def test_only_an_active_account_can_be_made_superadmin(client, root, session_factory) -> None:
    insert_account(session_factory, "gone@x.com", "admin", is_active=False)
    uid = _id_of(session_factory, "gone@x.com")
    assert client.post(f"{API}/auth/users/{uid}/superadmin", headers=root).status_code == 409


@pytest.mark.parametrize("actor_role", ["user", "admin"])
def test_only_a_superadmin_can_grant_or_revoke_superadmin(client, root, session_factory, actor_role) -> None:
    insert_account(session_factory, "actor@x.com", actor_role)
    insert_account(session_factory, "target@x.com", "user")
    insert_account(session_factory, "other-su@x.com", "superadmin")
    headers = _login(client, "actor@x.com")
    for email in ("target@x.com", "actor@x.com", "other-su@x.com"):
        uid = _id_of(session_factory, email)
        assert client.post(f"{API}/auth/users/{uid}/superadmin", headers=headers).status_code == 403
        assert client.delete(f"{API}/auth/users/{uid}/superadmin", headers=headers).status_code == 403
    assert _audit(session_factory, audit_service.ACTION_SUPERADMIN_GRANTED) == []


def _stale(session_factory, email: str) -> User:
    """A detached copy of an account as it was loaded earlier (what a racing request holds)."""
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        session.expunge(user)
        return user


def _set_role(session_factory, email: str, role: str) -> None:
    with session_factory() as session:
        session.scalar(select(User).where(User.email == email)).role = role
        session.commit()


def test_the_last_superadmin_cannot_be_demoted_even_when_the_actor_is_stale(session_factory, make_settings) -> None:
    """Two superadmins revoke each other at the same time. Each request has already passed its
    permission check, so the second one must be stopped by the last-superadmin guard."""
    a = insert_account(session_factory, "a@x.com", "superadmin")
    insert_account(session_factory, "b@x.com", "superadmin")
    b_stale = _stale(session_factory, "b@x.com")  # B still believes it is a superadmin...
    _set_role(session_factory, "b@x.com", "admin")  # ...but A's revocation has just committed.

    with session_factory() as session:
        with pytest.raises(ConflictError, match="last active superadmin"):
            auth_service.revoke_superadmin(session, b_stale, a.id)
        session.rollback()
    with session_factory() as session:
        assert session.scalar(select(User.role).where(User.email == "a@x.com")) == "superadmin"
    assert _audit(session_factory, audit_service.ACTION_SUPERADMIN_REVOKED) == []


def test_the_last_superadmin_cannot_be_deactivated_even_when_the_actor_is_stale(session_factory, make_settings) -> None:
    a = insert_account(session_factory, "a@x.com", "superadmin")
    insert_account(session_factory, "b@x.com", "superadmin")
    b_stale = _stale(session_factory, "b@x.com")
    _set_role(session_factory, "b@x.com", "admin")
    with session_factory() as session:
        with pytest.raises(ConflictError, match="last active superadmin"):
            auth_service.update_user(
                session, b_stale, a.id, UserUpdateRequest(is_active=False), make_settings(APP_ENV="testing")
            )
        session.rollback()
    with session_factory() as session:
        assert session.scalar(select(User.is_active).where(User.email == "a@x.com")) is True


def test_with_two_superadmins_one_can_demote_the_other(client, root, session_factory) -> None:
    insert_account(session_factory, "b@x.com", "superadmin")
    b_id = _id_of(session_factory, "b@x.com")
    assert client.delete(f"{API}/auth/users/{b_id}/superadmin", headers=root).status_code == 200
    # Exactly one superadmin remains and the API now refuses any attempt that would remove it.
    root_id = _id_of(session_factory, "root@x.com")
    assert client.delete(f"{API}/auth/users/{root_id}/superadmin", headers=root).status_code == 403


# --- deleting accounts -------------------------------------------------------------------------


def test_deletion_is_narrow_and_explicit(client, root, session_factory) -> None:
    insert_account(session_factory, "del@x.com", "user")
    uid = _id_of(session_factory, "del@x.com")
    # still active
    assert client.delete(f"{API}/auth/users/{uid}?confirm_email=del@x.com", headers=root).status_code == 409
    client.patch(f"{API}/auth/users/{uid}", json={"is_active": False}, headers=root)
    # wrong confirmation
    assert client.delete(f"{API}/auth/users/{uid}?confirm_email=other@x.com", headers=root).status_code == 422
    # no confirmation at all
    assert client.delete(f"{API}/auth/users/{uid}", headers=root).status_code == 422
    assert _id_of(session_factory, "del@x.com") == uid

    ok = client.delete(f"{API}/auth/users/{uid}?confirm_email=DEL@x.com", headers=root)
    assert ok.status_code == 204
    with session_factory() as session:
        assert session.scalar(select(User).where(User.email == "del@x.com")) is None
    deleted = _audit(session_factory, audit_service.ACTION_DELETED)
    assert len(deleted) == 1 and deleted[0].target_email == "del@x.com"
    assert deleted[0].before["role"] == "user" and str(deleted[0].target_id) == uid, "the audit row outlives the user"


def test_an_account_that_owns_resources_cannot_be_deleted(client, root, session_factory) -> None:
    from app.database.models.dataset import Dataset

    owner = insert_account(session_factory, "owner@x.com", "admin")
    with session_factory() as session:
        session.add(
            Dataset(
                name="d", original_filename="d.csv", stored_filename="d-stored.csv", file_format="csv",
                size_bytes=1, sha256="0" * 64, n_rows=1, n_columns=1, columns=[], owner_id=owner.id,
            )
        )
        session.commit()
    client.patch(f"{API}/auth/users/{owner.id}", json={"is_active": False}, headers=root)
    r = client.delete(f"{API}/auth/users/{owner.id}?confirm_email=owner@x.com", headers=root)
    assert r.status_code == 409 and "1 datasets" in r.text
    assert _id_of(session_factory, "owner@x.com") == str(owner.id)


def test_a_superadmin_cannot_be_deleted(client, root, session_factory) -> None:
    insert_account(session_factory, "su2@x.com", "superadmin", is_active=False)
    uid = _id_of(session_factory, "su2@x.com")
    assert client.delete(f"{API}/auth/users/{uid}?confirm_email=su2@x.com", headers=root).status_code == 409


# --- audit trail ---------------------------------------------------------------------------------


def test_a_failed_operation_leaves_neither_the_change_nor_an_audit_entry(
    make_client, session_factory, monkeypatch
) -> None:
    insert_account(session_factory, "root@x.com", "superadmin")
    insert_account(session_factory, "t@x.com", "user")
    with make_client() as client:
        headers = _login(client, "root@x.com")
        uid = _id_of(session_factory, "t@x.com")

        def boom(*args, **kwargs):
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_service, "record", boom)
        failed = client.patch(f"{API}/auth/users/{uid}", json={"role": "admin"}, headers=headers)
    assert failed.status_code == 500
    with session_factory() as session:
        assert session.scalar(select(User.role).where(User.email == "t@x.com")) == "user", "change must roll back"
    assert _audit(session_factory) == []


def test_audit_log_is_readable_only_by_superadmins_and_is_read_only(client, root, session_factory) -> None:
    insert_account(session_factory, "adm@x.com", "admin")
    insert_account(session_factory, "usr@x.com", "user")
    for who in ("adm@x.com", "usr@x.com"):
        assert client.get(f"{API}/audit-logs", headers=_login(client, who)).status_code == 403
    assert client.get(f"{API}/audit-logs").status_code == 401

    uid = _id_of(session_factory, "usr@x.com")
    client.patch(f"{API}/auth/users/{uid}", json={"role": "admin"}, headers=root)
    page = client.get(f"{API}/audit-logs?action=user.role_changed", headers=root).json()
    assert page["total"] == 1 and page["items"][0]["target_email"] == "usr@x.com"
    assert page["items"][0]["request_id"], "entries carry the request id for tracing"

    for method in ("put", "patch", "delete", "post"):
        assert getattr(client, method)(f"{API}/audit-logs", headers=root).status_code == 405


def test_audit_entries_never_contain_password_material(client, root, session_factory) -> None:
    client.post(f"{API}/auth/users", json={"email": "p@x.com", "password": PASSWORD, "role": "user"}, headers=root)
    dump = repr([(e.before, e.after, e.detail) for e in _audit(session_factory)])
    assert PASSWORD not in dump and "argon2" not in dump and "pbkdf2" not in dump


# --- system settings -----------------------------------------------------------------------------


def test_system_settings_are_superadmin_only_and_never_expose_secrets(make_client, session_factory) -> None:
    secrets = {
        "JWT_SECRET_KEY": "sentinel-jwt-secret-value-0123456789abcdef",
        "METRICS_TOKEN": "sentinel-metrics-token",
        "OPENAI_API_KEY": "sk-sentinel-openai-key-value",
    }
    insert_account(session_factory, "root@x.com", "superadmin")
    insert_account(session_factory, "adm@x.com", "admin")
    with make_client(**secrets) as client:
        assert client.get(f"{API}/system/settings", headers=_login(client, "adm@x.com")).status_code == 403
        assert client.get(f"{API}/system/settings").status_code == 401
        response = client.get(f"{API}/system/settings", headers=_login(client, "root@x.com"))
    assert response.status_code == 200
    body = response.json()
    assert body["metrics_token_configured"] is True
    for value in secrets.values():
        assert value not in response.text
    # An explicit allow-list: any new field must be added here deliberately, after checking it is not secret.
    assert set(body) == {
        "app_name", "environment", "version", "release", "docs_enabled", "log_level", "rate_limit_enabled",
        "rate_limits_per_minute", "max_upload_size_mb", "max_dataset_rows", "max_dataset_columns",
        "max_prediction_records", "access_token_minutes", "refresh_token_days", "job_inline_dispatch",
        "job_stale_timeout_minutes", "database_pool_size", "database_max_overflow",
        "metrics_token_configured", "password_rehash_on_login", "rbac_store_legacy_viewer", "llm_provider",
    }


# --- compatibility with databases that predate RBAC v2 (expand phase) --------------------------


@pytest.mark.parametrize(("stored", "reported"), [("viewer", "user"), ("ml_engineer", "user")])
def test_legacy_stored_roles_are_reported_with_the_current_names(client, session_factory, stored, reported) -> None:
    with session_factory() as session:
        # Bypass the model CHECK (it permits "viewer" only) by writing through the ORM default path.
        pass
    if stored == "viewer":
        insert_account(session_factory, "old@x.com", "viewer")
    else:
        # ml_engineer is rejected by the new CHECK in a migrated schema; simulate a pre-migration database.
        from sqlalchemy import text

        with session_factory() as session:
            session.execute(text("PRAGMA ignore_check_constraints = ON"))
            insert_account(session_factory, "old@x.com", "user")
            session.execute(text("UPDATE users SET role = 'ml_engineer' WHERE email = 'old@x.com'"))
            session.commit()
    me = client.get(f"{API}/auth/me", headers=_login(client, "old@x.com")).json()
    assert me["role"] == reported
    assert "ml:operate" not in me["permissions"], "legacy accounts are never promoted"
    assert "users:manage" not in me["permissions"]


def test_an_unknown_stored_role_gets_no_permissions_at_all(client, session_factory) -> None:
    from sqlalchemy import text

    insert_account(session_factory, "weird@x.com", "user")
    with session_factory() as session:
        session.execute(text("PRAGMA ignore_check_constraints = ON"))
        session.execute(text("UPDATE users SET role = 'overlord' WHERE email = 'weird@x.com'"))
        session.commit()
    headers = _login(client, "weird@x.com")
    for path in ("auth/me", "models", "datasets", "jobs"):
        assert client.get(f"{API}/{path}", headers=headers).status_code == 403, path


def test_expand_switch_stores_new_users_under_the_old_name_but_reports_user(make_client, session_factory) -> None:
    insert_account(session_factory, "root@x.com", "superadmin")
    with make_client(RBAC_STORE_LEGACY_VIEWER=True) as client:
        registered = client.post(f"{API}/auth/register", json={"email": "new@x.com", "password": PASSWORD})
        assert registered.status_code == 201 and registered.json()["role"] == "user"
        headers = _login(client, "root@x.com")
        made = client.post(f"{API}/auth/users", json={"email": "adm@x.com", "password": PASSWORD, "role": "admin"}, headers=headers)
        assert made.json()["role"] == "admin"
    with session_factory() as session:
        stored = dict(session.execute(select(User.email, User.role)).all())
    assert stored["new@x.com"] == "viewer", "pre-RBAC-v2 releases can still read it"
    assert stored["adm@x.com"] == "admin"


def test_user_filter_finds_legacy_and_current_rows(client, root, session_factory) -> None:
    insert_account(session_factory, "legacy@x.com", "viewer")
    insert_account(session_factory, "current@x.com", "user")
    emails = {u["email"] for u in client.get(f"{API}/auth/users?role=user", headers=root).json()["items"]}
    assert {"legacy@x.com", "current@x.com"} <= emails
    assert "root@x.com" not in emails


# --- public registration -------------------------------------------------------------------------


def test_registration_always_creates_a_user_and_is_not_audited_as_a_privileged_event(client, session_factory) -> None:
    r = client.post(f"{API}/auth/register", json={"email": "pub@x.com", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["role"] == "user"
    assert _audit(session_factory) == []
    unique = uuid.uuid4().hex[:6]
    for key in ("role", "permissions", "is_active", "is_superuser"):
        bad = client.post(
            f"{API}/auth/register", json={"email": f"{unique}-{key}@x.com", "password": PASSWORD, key: "superadmin"}
        )
        assert bad.status_code == 422
