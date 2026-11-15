"""scripts/create_super_admin.py: production bootstrap without public registration."""

import importlib.util
from pathlib import Path

import pytest

from app.database.models import AuditLog, User

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def script(monkeypatch, tmp_path, session_factory):
    spec = importlib.util.spec_from_file_location(
        "create_super_admin", ROOT / "scripts" / "create_super_admin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_session_factory", lambda: session_factory)
    return module


def test_creates_super_admin_from_env_password(script, monkeypatch, session_factory) -> None:
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "Str0ngPassword!")
    assert script.main(["--email", "Ops@Example.com", "--full-name", "Ops"]) == 0
    with session_factory() as session:
        user = session.query(User).one()
        audit = session.query(AuditLog).one()
    assert (user.email, user.role, user.is_active) == ("ops@example.com", "super_admin", True)
    assert user.hashed_password.startswith("$argon2id$")
    assert audit.action == "user.create_cli"
    # Running again does not create a duplicate.
    assert script.main(["--email", "ops@example.com"]) == 1


def test_rejects_weak_password_and_bad_email(script, monkeypatch, session_factory) -> None:
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "weak")
    assert script.main(["--email", "ops@example.com"]) == 1
    assert script.main(["--email", "not-an-email"]) == 1
    with session_factory() as session:
        assert session.query(User).count() == 0


def test_promotes_existing_account_and_ends_its_sessions(script, session_factory) -> None:
    with session_factory() as session:
        session.add(User(email="u@x.com", hashed_password="x", role="user", is_active=False))
        session.commit()
    assert script.main(["--email", "u@x.com", "--promote"]) == 0
    with session_factory() as session:
        user = session.query(User).one()
    assert (user.role, user.is_active, user.token_version) == ("super_admin", True, 1)
    assert script.main(["--email", "missing@x.com", "--promote"]) == 1

