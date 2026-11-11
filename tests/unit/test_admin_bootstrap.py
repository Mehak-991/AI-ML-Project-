"""First-administrator bootstrap: explicit and one-time, never through public registration."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.exceptions import ConflictError, DataValidationError
from app.database.models.user import User
from app.database.session import get_db
from app.main import create_app
from app.services import auth_service

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd"


@pytest.fixture
def secure_client(make_settings, session_factory):
    """Settings as shipped."""
    settings = make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False)
    app = create_app(settings)

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _factory_stub(session_factory):
    """Stands in for the cached get_session_factory (the shared fixtures call cache_clear on it)."""

    def _get():
        return session_factory

    _get.cache_clear = lambda: None
    return _get


def _register(client, email, **fields):
    return client.post(f"{API}/auth/register", json={"email": email, "password": PASSWORD, **fields})


def test_first_public_registration_on_an_empty_database_is_only_a_user(secure_client) -> None:
    response = _register(secure_client, "visitor@x.com")
    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_first_registration_cannot_request_admin_either(secure_client) -> None:
    response = _register(secure_client, "visitor@x.com", role="admin")
    assert response.status_code == 422  # the public payload has no role field at all
    assert secure_client.post(
        f"{API}/auth/login", json={"email": "visitor@x.com", "password": PASSWORD}
    ).status_code == 401, "a rejected registration must not leave an account behind"


def test_nobody_becomes_admin_by_registering_many_times(secure_client) -> None:
    roles = {_register(secure_client, f"u{i}@x.com").json()["role"] for i in range(3)}
    assert roles == {"user"}


def test_bootstrap_creates_one_admin_who_can_log_in(secure_client, session_factory) -> None:
    with session_factory() as session:
        admin = auth_service.create_bootstrap_admin(session, "Root@X.com ", PASSWORD, "Root")
        assert admin.role == "admin" and admin.email == "root@x.com" and admin.is_active
        assert admin.hashed_password.startswith("$argon2id$")
    login = secure_client.post(f"{API}/auth/login", json={"email": "root@x.com", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"


def test_bootstrap_is_one_time(session_factory) -> None:
    with session_factory() as session:
        auth_service.create_bootstrap_admin(session, "root@x.com", PASSWORD)
        with pytest.raises(ConflictError, match="one-time"):
            auth_service.create_bootstrap_admin(session, "second@x.com", PASSWORD)
        assert session.scalar(select(User).where(User.email == "second@x.com")) is None


def test_bootstrap_never_promotes_or_changes_an_existing_account(secure_client, session_factory) -> None:
    _register(secure_client, "member@x.com")
    with session_factory() as session:
        before = session.scalar(select(User).where(User.email == "member@x.com")).hashed_password
        with pytest.raises(ConflictError, match="not changed"):
            auth_service.create_bootstrap_admin(session, "member@x.com", "Different1Password")
    with session_factory() as session:
        member = session.scalar(select(User).where(User.email == "member@x.com"))
        assert member.role == "user" and member.hashed_password == before


def test_bootstrap_rejects_weak_passwords(session_factory) -> None:
    with session_factory() as session:
        with pytest.raises(DataValidationError):
            auth_service.create_bootstrap_admin(session, "root@x.com", "short")
        assert session.scalar(select(User)) is None


@pytest.mark.parametrize("email", ["admin@example.test", "not-an-email", "a@localhost", ""])
def test_bootstrap_rejects_addresses_the_login_endpoint_would_reject(
    secure_client, session_factory, email
) -> None:
    """An admin created with such an address could never sign in."""
    with session_factory() as session:
        with pytest.raises(DataValidationError, match="email"):
            auth_service.create_bootstrap_admin(session, email, PASSWORD)
        assert session.scalar(select(User)) is None
    if email:
        login = secure_client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 422, "the API itself rejects this address, so the CLI must too"


def test_bootstrap_still_allowed_when_only_inactive_admins_exist(session_factory) -> None:
    """Recovery: the last admin was deactivated and nobody can administer the system."""
    with session_factory() as session:
        old = auth_service.create_bootstrap_admin(session, "old@x.com", PASSWORD)
        old.is_active = False
        session.commit()
        new = auth_service.create_bootstrap_admin(session, "new@x.com", PASSWORD)
        assert new.role == "admin"


def test_script_reports_refusal_without_leaking_the_password(
    monkeypatch, session_factory, capsys
) -> None:
    from scripts import create_admin

    secret = "S3cretBootstrapValue"
    monkeypatch.setenv(create_admin.PASSWORD_ENV, secret)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.invalid/x")
    monkeypatch.setattr("app.database.session.get_session_factory", _factory_stub(session_factory))

    assert create_admin.main(["--email", "root@x.com"]) == 0
    assert create_admin.main(["--email", "other@x.com"]) == 1  # one-time
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert "Created administrator root@x.com" in captured.out
    assert "Refused" in captured.err


def test_script_without_a_password_source_exits_cleanly(monkeypatch, session_factory, capsys) -> None:
    from scripts import create_admin

    monkeypatch.delenv(create_admin.PASSWORD_ENV, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.invalid/x")
    monkeypatch.setattr("sys.stdin", type("NoTTY", (), {"isatty": lambda self: False})())
    monkeypatch.setattr("app.database.session.get_session_factory", _factory_stub(session_factory))
    assert create_admin.main(["--email", "root@x.com"]) == 1
    assert "No password supplied" in capsys.readouterr().err
