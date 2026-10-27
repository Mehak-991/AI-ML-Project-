"""Full application lifecycle (startup -> requests -> shutdown) without external services."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_startup_and_shutdown_cycle(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        for path in ("/", "/health", "/api/v1/health"):
            assert client.get(path).status_code == 200
    # Lifespan shutdown ran without error; a fresh client can start again.
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
