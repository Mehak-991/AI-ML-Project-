import pytest

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError
from app.database import session as db_session
from app.database.base import Base


def test_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    get_settings.cache_clear()
    with pytest.raises(DatabaseNotConfiguredError):
        db_session.get_engine()


def test_session_lifecycle_with_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    # SQLite stands in for PostgreSQL so the session plumbing is tested without a server.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()

    assert db_session.check_database_connection() is True
    sessions = db_session.get_db()
    session = next(sessions)
    assert session.is_active
    sessions.close()
    db_session.dispose_engine()


def test_metadata_has_naming_convention() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
