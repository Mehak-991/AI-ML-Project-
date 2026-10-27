"""PostgreSQL integration tests. Skipped unless TEST_DATABASE_URL points at a disposable DB."""

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@requires_db
def test_readiness_against_real_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["components"]["database"] == "ok"
