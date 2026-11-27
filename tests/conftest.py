"""Shared fixtures. Tests never read the developer's .env or shell settings.

Database note: unit/API tests use an in-memory **SQLite** database purely as a
test double for PostgreSQL. The application itself refuses non-PostgreSQL URLs
in production. Real PostgreSQL tests live in tests/integration and run only
when TEST_DATABASE_URL is set.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.database.models import Base
from app.database.session import dispose_engine, get_db
from app.main import create_app
from app.ml.persistence import clear_artifact_cache
from app.ml.synthetic import make_classification_frame, make_regression_frame

# Every environment variable the application reads: all Settings fields. Derived from the
# model (not a hand-written list) so CI variables such as RATE_LIMIT_ENABLED=false or a
# developer's shell exports can never leak into tests when new settings are added.
SETTINGS_ENV_VARS = sorted(Settings.model_fields)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Never read the developer's .env: code paths that use the global get_settings()
    # (e.g. the DB session layer) would otherwise reach a real database or provider.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    dispose_engine()
    clear_artifact_cache()
    yield
    get_settings.cache_clear()
    dispose_engine()
    clear_artifact_cache()


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argon2id with test-sized cost. Production parameters live in app.core.security."""
    from argon2 import PasswordHasher

    from app.core import security

    monkeypatch.setattr(
        security, "_argon2", PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    )


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    """Settings isolated from .env, with storage directories under tmp_path."""

    def _make(**overrides: object) -> Settings:
        overrides.setdefault("UPLOAD_DIR", tmp_path / "uploads")
        overrides.setdefault("MODEL_DIR", tmp_path / "models")
        # Unit tests never probe a real Ollama server from the readiness endpoint.
        overrides.setdefault("OLLAMA_HEALTHCHECK_ENABLED", False)
        # A strong per-test secret so production-mode settings validate; tests about weak
        # secrets pass JWT_SECRET_KEY explicitly.
        overrides.setdefault("JWT_SECRET_KEY", "test-only-secret-" + "x" * 40)
        return Settings(_env_file=None, **overrides)

    return _make


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    return make_settings(APP_ENV="testing", APP_NAME="AIProject Test")


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


# --- Database (SQLite test double) -------------------------------------------------


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def api_client(app: FastAPI, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """Client whose get_db and auth dependencies are backed by the SQLite test database."""
    from typing import Any
    from datetime import datetime, timezone
    from app.api.deps import get_current_user, get_current_user_optional
    from app.database.models.user import User
    import uuid

    mock_admin = User(
        id=uuid.uuid4(),
        email="test_admin@example.com",
        full_name="Test Admin",
        hashed_password="mock",
        role="super_admin",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    def _get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    from typing import Annotated
    from fastapi import Security
    from fastapi.security import HTTPAuthorizationCredentials
    from app.api.deps import DbSession, SettingsDep, security_bearer

    real_get_current_user = get_current_user
    real_get_current_user_optional = get_current_user_optional

    def _conditional_get_current_user(
        auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
        db: DbSession,
        settings: SettingsDep,
    ):
        if auth and auth.credentials:
            return real_get_current_user(auth, db, settings)
        return mock_admin

    def _conditional_get_current_user_optional(
        auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_bearer)],
        db: DbSession,
        settings: SettingsDep,
    ):
        if auth and auth.credentials:
            return real_get_current_user_optional(auth, db, settings)
        return mock_admin

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _conditional_get_current_user
    app.dependency_overrides[get_current_user_optional] = _conditional_get_current_user_optional

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# --- Data ------------------------------------------------------------------------


@pytest.fixture
def classification_df() -> pd.DataFrame:
    return make_classification_frame(n_rows=200, seed=7)


@pytest.fixture
def regression_df() -> pd.DataFrame:
    return make_regression_frame(n_rows=200, seed=7)
