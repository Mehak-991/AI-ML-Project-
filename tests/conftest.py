"""Shared fixtures. Tests never read the developer's .env or shell settings."""

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.database.session import dispose_engine
from app.main import create_app

SETTINGS_ENV_VARS = [
    "APP_NAME",
    "APP_ENV",
    "DEBUG",
    "API_V1_PREFIX",
    "LOG_LEVEL",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "DATABASE_CONNECT_TIMEOUT",
    "OPENAI_API_KEY",
]


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    dispose_engine()
    yield
    get_settings.cache_clear()
    dispose_engine()


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    def _make(**overrides: object) -> Settings:
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
