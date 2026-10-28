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

SETTINGS_ENV_VARS = [
    "APP_NAME",
    "APP_ENV",
    "DEBUG",
    "API_V1_PREFIX",
    "LOG_LEVEL",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "DATABASE_CONNECT_TIMEOUT",
    "DATABASE_POOL_SIZE",
    "DATABASE_MAX_OVERFLOW",
    "DATABASE_ECHO",
    "UPLOAD_DIR",
    "MODEL_DIR",
    "MAX_UPLOAD_SIZE_MB",
    "MAX_DATASET_ROWS",
    "MAX_DATASET_COLUMNS",
    "MAX_PREDICTION_RECORDS",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_ALLOWED_MODELS",
    "LLM_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_ALLOWED_MODELS",
    "OLLAMA_TIMEOUT_SECONDS",
]


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


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    """Settings isolated from .env, with storage directories under tmp_path."""

    def _make(**overrides: object) -> Settings:
        overrides.setdefault("UPLOAD_DIR", tmp_path / "uploads")
        overrides.setdefault("MODEL_DIR", tmp_path / "models")
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
    """Client whose get_db dependency is backed by the SQLite test database."""

    def _get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


# --- Data ------------------------------------------------------------------------


@pytest.fixture
def classification_df() -> pd.DataFrame:
    return make_classification_frame(n_rows=200, seed=7)


@pytest.fixture
def regression_df() -> pd.DataFrame:
    return make_regression_frame(n_rows=200, seed=7)
