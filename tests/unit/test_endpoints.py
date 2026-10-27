from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Settings
from app.database import session as db_session
from app.main import create_app
from app.schemas.common import RootResponse
from app.schemas.health import HealthResponse, ReadinessResponse


def test_app_module_imports() -> None:
    import app.main

    assert app.main.app.title
    assert app.main.app.version == __version__


def test_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = RootResponse.model_validate(response.json())
    assert body.name == "AIProject Test"
    assert body.version == __version__
    assert body.health_url == "/api/v1/health"


def test_liveness(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = HealthResponse.model_validate(response.json())
    assert body.status == "ok"
    assert body.environment == "testing"
    assert isinstance(body.timestamp, datetime)
    assert body.timestamp.tzinfo is not None


def test_readiness_without_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = ReadinessResponse.model_validate(response.json())
    assert body.status == "ok"
    assert body.components == {"database": "not_configured"}


@pytest.mark.parametrize(("reachable", "status_code", "state"), [(True, 200, "ok"), (False, 503, "unavailable")])
def test_readiness_with_mocked_database(
    monkeypatch: pytest.MonkeyPatch,
    make_settings,
    reachable: bool,
    status_code: int,
    state: str,
) -> None:
    calls = []

    def fake_check() -> bool:
        calls.append(1)
        return reachable

    monkeypatch.setattr(db_session, "check_database_connection", fake_check)
    settings = make_settings(APP_ENV="testing", DATABASE_URL="postgresql://u:p@db.invalid/x")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert calls == [1]
    assert response.status_code == status_code
    body = ReadinessResponse.model_validate(response.json())
    assert body.components["database"] == state
    assert body.status == ("ok" if reachable else "unavailable")
    assert "db.invalid" not in response.text


def test_custom_api_prefix(make_settings) -> None:
    settings: Settings = make_settings(API_V1_PREFIX="/v1")
    with TestClient(create_app(settings)) as client:
        assert client.get("/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 404


def test_docs_and_openapi(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == __version__
    assert {"/", "/health", "/api/v1/health"} <= set(schema["paths"])


def test_cors_allows_configured_origin(make_settings) -> None:
    settings = make_settings(CORS_ORIGINS="https://allowed.example")
    with TestClient(create_app(settings)) as client:
        allowed = client.get("/health", headers={"Origin": "https://allowed.example"})
        denied = client.get("/health", headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "https://allowed.example"
    assert "access-control-allow-origin" not in denied.headers


def test_no_cors_headers_by_default_in_production(make_settings) -> None:
    settings = make_settings(APP_ENV="production", DATABASE_URL="postgresql://u:p@h/db")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in response.headers
