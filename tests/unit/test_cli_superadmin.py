"""The server-side superadmin bootstrap and password-reset CLIs (never exposed through the API)."""

import sys

import pytest
from sqlalchemy import select, text

from app.database.models.audit import AuditLog
from app.database.models.user import RefreshToken, User
from scripts import create_superadmin, reset_password
from tests.helpers import DEFAULT_TEST_PASSWORD, insert_account

SECRET = "Sup3rS3cretBootstrapValue"


def _factory_stub(session_factory):
    """Stands in for the cached get_session_factory (shared fixtures call cache_clear on it)."""

    def _get():
        return session_factory

    _get.cache_clear = lambda: None
    return _get


@pytest.fixture
def cli_env(monkeypatch, session_factory):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db.invalid/x")
    monkeypatch.setattr("app.database.session.get_session_factory", _factory_stub(session_factory))
    monkeypatch.delenv(create_superadmin.PASSWORD_ENV, raising=False)
    monkeypatch.delenv(reset_password.PASSWORD_ENV, raising=False)
    return session_factory


class _Tty:
    def isatty(self) -> bool:
        return True


def _row(session_factory, email: str) -> User | None:
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is not None:
            session.expunge(user)
        return user


def _audit(session_factory) -> list[AuditLog]:
    with session_factory() as session:
        return list(session.scalars(select(AuditLog).order_by(AuditLog.created_at)).all())


# --- create_superadmin: new account ----------------------------------------------------------


def test_creates_a_new_superadmin_and_never_prints_the_password(cli_env, monkeypatch, capsys) -> None:
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", "Boss@X.com", "--full-name", "The Boss"]) == 0
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert "Created superadmin boss@x.com" in captured.out

    user = _row(cli_env, "boss@x.com")
    assert user.role == "superadmin" and user.is_active and user.full_name == "The Boss"
    assert user.hashed_password.startswith("$argon2id$")
    (entry,) = _audit(cli_env)
    assert entry.action == "cli.superadmin_bootstrap" and entry.actor_email == "cli"
    assert entry.after == {"role": "superadmin"} and entry.target_email == "boss@x.com"
    assert SECRET not in repr((entry.before, entry.after, entry.detail))


def test_bootstrap_is_one_time(cli_env, monkeypatch, capsys) -> None:
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", "first@x.com"]) == 0
    assert create_superadmin.main(["--email", "second@x.com"]) == 1
    assert "one-time" in capsys.readouterr().err
    assert _row(cli_env, "second@x.com") is None


def test_it_is_also_the_recovery_path_when_no_active_superadmin_is_left(cli_env, monkeypatch) -> None:
    lost = insert_account(cli_env, "lost@x.com", "superadmin", is_active=False)
    insert_account(cli_env, "adm@x.com", "admin")
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", "back@x.com"]) == 0
    assert _row(cli_env, "back@x.com").role == "superadmin"
    assert _row(cli_env, "adm@x.com").role == "admin", "nobody else is promoted"
    assert _row(cli_env, "lost@x.com").is_active is False and lost.email == "lost@x.com"


def test_refuses_before_migration_0014(cli_env, monkeypatch, capsys) -> None:
    with cli_env() as session:
        session.execute(text("DROP TABLE audit_logs"))
        session.commit()
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", "early@x.com"]) == 1
    assert "migration 0014" in capsys.readouterr().err
    assert _row(cli_env, "early@x.com") is None


@pytest.mark.parametrize("bad", ["short", "alllowercase1", "NOLOWERCASE1", "NoDigitsHere"])
def test_weak_passwords_are_refused(cli_env, monkeypatch, bad) -> None:
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, bad)
    assert create_superadmin.main(["--email", "weak@x.com"]) == 1
    assert _row(cli_env, "weak@x.com") is None


@pytest.mark.parametrize("email", ["admin@example.test", "not-an-email", "a@localhost"])
def test_addresses_the_login_endpoint_rejects_are_refused(cli_env, monkeypatch, email) -> None:
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", email]) == 1
    assert _audit(cli_env) == []


def test_without_a_password_source_it_exits_cleanly(cli_env, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", type("NoTty", (), {"isatty": lambda self: False})())
    assert create_superadmin.main(["--email", "nopw@x.com"]) == 1
    assert "No password supplied" in capsys.readouterr().err


def test_an_existing_account_is_never_overwritten_in_create_mode(cli_env, monkeypatch) -> None:
    existing = insert_account(cli_env, "taken@x.com", "user")
    monkeypatch.setenv(create_superadmin.PASSWORD_ENV, SECRET)
    assert create_superadmin.main(["--email", "taken@x.com"]) == 1
    after = _row(cli_env, "taken@x.com")
    assert after.role == "user" and after.hashed_password == existing.hashed_password


def test_it_never_chooses_an_account_for_you() -> None:
    with pytest.raises(SystemExit) as exit_info:
        create_superadmin.main([])  # --email is required
    assert exit_info.value.code == 2


# --- create_superadmin: promoting one explicit existing account ------------------------------


def test_promotion_needs_confirmation_and_is_refused_without_a_terminal(cli_env, monkeypatch, capsys) -> None:
    insert_account(cli_env, "adm@x.com", "admin")
    monkeypatch.setattr(sys, "stdin", type("NoTty", (), {"isatty": lambda self: False})())
    assert create_superadmin.main(["--email", "adm@x.com", "--promote"]) == 1
    assert "confirmation" in capsys.readouterr().err
    assert _row(cli_env, "adm@x.com").role == "admin"


def test_interactive_confirmation_must_match_the_email(cli_env, monkeypatch) -> None:
    insert_account(cli_env, "adm@x.com", "admin")
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda prompt="": "someone-else@x.com")
    assert create_superadmin.main(["--email", "adm@x.com", "--promote"]) == 1
    assert _row(cli_env, "adm@x.com").role == "admin"

    monkeypatch.setattr("builtins.input", lambda prompt="": "ADM@x.com")
    assert create_superadmin.main(["--email", "adm@x.com", "--promote"]) == 0
    assert _row(cli_env, "adm@x.com").role == "superadmin"


def test_promotion_changes_only_that_role_and_keeps_the_password(cli_env, capsys) -> None:
    target = insert_account(cli_env, "adm@x.com", "admin")
    insert_account(cli_env, "other-adm@x.com", "admin")
    insert_account(cli_env, "usr@x.com", "user")
    assert create_superadmin.main(["--email", "adm@x.com", "--promote", "--yes"]) == 0
    assert "Promoted superadmin adm@x.com" in capsys.readouterr().out
    promoted = _row(cli_env, "adm@x.com")
    assert promoted.role == "superadmin" and promoted.hashed_password == target.hashed_password
    assert _row(cli_env, "other-adm@x.com").role == "admin"
    assert _row(cli_env, "usr@x.com").role == "user"
    (entry,) = _audit(cli_env)
    assert entry.before == {"role": "admin"} and entry.after == {"role": "superadmin"}
    assert entry.detail == "promoted existing account"


def test_promoting_a_missing_or_deactivated_account_is_refused(cli_env, capsys) -> None:
    insert_account(cli_env, "off@x.com", "admin", is_active=False)
    assert create_superadmin.main(["--email", "ghost@x.com", "--promote", "--yes"]) == 1
    assert create_superadmin.main(["--email", "off@x.com", "--promote", "--yes"]) == 1
    assert _row(cli_env, "off@x.com").role == "admin"
    assert _audit(cli_env) == []


def test_promotion_is_refused_when_a_superadmin_exists(cli_env) -> None:
    insert_account(cli_env, "root@x.com", "superadmin")
    insert_account(cli_env, "adm@x.com", "admin")
    assert create_superadmin.main(["--email", "adm@x.com", "--promote", "--yes"]) == 1
    assert _row(cli_env, "adm@x.com").role == "admin"


# --- reset_password ---------------------------------------------------------------------------


def test_password_reset_revokes_sessions_is_audited_and_prints_nothing_secret(cli_env, monkeypatch, capsys, session_factory) -> None:
    user = insert_account(cli_env, "root@x.com", "superadmin")
    with cli_env() as session:
        session.add(RefreshToken(user_id=user.id, token_hash="h" * 64, expires_at="2099-01-01T00:00:00+00:00", revoked=False))
        session.commit()
    monkeypatch.setenv(reset_password.PASSWORD_ENV, SECRET)
    assert reset_password.main(["--email", "root@x.com"]) == 0
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err

    after = _row(cli_env, "root@x.com")
    assert after.role == "superadmin" and after.is_active
    assert after.hashed_password != user.hashed_password
    from app.core import security

    assert security.verify_password(SECRET, after.hashed_password)
    assert not security.verify_password(DEFAULT_TEST_PASSWORD, after.hashed_password)
    with cli_env() as session:
        assert all(t.revoked for t in session.scalars(select(RefreshToken)).all())
    (entry,) = _audit(cli_env)
    assert entry.action == "cli.password_reset" and entry.actor_email == "cli" and entry.target_email == "root@x.com"
    assert SECRET not in repr((entry.before, entry.after, entry.detail))


def test_password_reset_refusals(cli_env, monkeypatch, capsys) -> None:
    insert_account(cli_env, "root@x.com", "superadmin")
    before = _row(cli_env, "root@x.com").hashed_password
    monkeypatch.setenv(reset_password.PASSWORD_ENV, SECRET)
    assert reset_password.main(["--email", "nobody@x.com"]) == 1  # unknown account
    monkeypatch.setenv(reset_password.PASSWORD_ENV, "weak")
    assert reset_password.main(["--email", "root@x.com"]) == 1  # weak password
    monkeypatch.delenv(reset_password.PASSWORD_ENV)
    monkeypatch.setattr(sys, "stdin", type("NoTty", (), {"isatty": lambda self: False})())
    assert reset_password.main(["--email", "root@x.com"]) == 1  # no password supplied
    assert _row(cli_env, "root@x.com").hashed_password == before
    assert _audit(cli_env) == []

    with cli_env() as session:
        session.execute(text("DROP TABLE audit_logs"))
        session.commit()
    monkeypatch.setenv(reset_password.PASSWORD_ENV, SECRET)
    assert reset_password.main(["--email", "root@x.com"]) == 1
    assert "migration 0014" in capsys.readouterr().err
