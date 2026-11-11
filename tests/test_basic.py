"""
Basic test suite — verifies the nine acceptance criteria:

1.  Python environment (import works)
2.  Core dependencies importable
3.  FastAPI application instantiates
4.  Root endpoint returns the welcome message
5.  Swagger docs URL is registered (/docs)
6.  SQLite connectivity
7.  PostgreSQL connectivity (skipped if TEST_DATABASE_URL not set)
8.  Ollama connection (skipped if Ollama is not running)
9.  Configured Ollama model is listed locally (skipped if Ollama is not running)

Run with:
    pytest tests/test_basic.py -v
"""

import os

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 1 & 3 — FastAPI app imports without error
# ---------------------------------------------------------------------------
def test_app_imports():
    from app.main import app  # noqa: F401

    assert app is not None


# ---------------------------------------------------------------------------
# 2 — Core ML/data-science packages importable
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("package", ["numpy", "pandas", "sklearn", "matplotlib", "seaborn"])
def test_core_packages_importable(package):
    __import__(package)


# ---------------------------------------------------------------------------
# 4 — Root endpoint returns the correct welcome message
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    from app.main import app

    return TestClient(app)


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to AI / ML Project"}


# ---------------------------------------------------------------------------
# 5 — /docs is registered (Swagger UI)
# ---------------------------------------------------------------------------
def test_swagger_ui_registered(client):
    response = client.get("/docs")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 6 — SQLite connectivity
# ---------------------------------------------------------------------------
def test_sqlite_connectivity(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    # Re-import so it picks up the patched env var.
    import importlib

    import app.database.database as db_mod

    importlib.reload(db_mod)
    result = db_mod.check_db_connection()
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# 7 — PostgreSQL connectivity (skipped when TEST_DATABASE_URL is not set)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping PostgreSQL test",
)
def test_postgresql_connectivity(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    import importlib

    import app.database.database as db_mod

    importlib.reload(db_mod)
    result = db_mod.check_db_connection()
    assert result["status"] == "ok", result.get("detail")


# ---------------------------------------------------------------------------
# 8 & 9 — Ollama connection and model availability
#          (skipped when local Ollama is not running)
# ---------------------------------------------------------------------------
def _ollama_running() -> bool:
    try:
        import httpx

        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_running(), reason="Local Ollama service is not running")
def test_ollama_connection():
    from app.services.ollama_service import check_ollama_connection

    result = check_ollama_connection()
    assert result["status"] == "ok", result.get("detail")


@pytest.mark.skipif(not _ollama_running(), reason="Local Ollama service is not running")
def test_ollama_model_available():
    from app.services.ollama_service import OLLAMA_MODEL, check_ollama_connection

    result = check_ollama_connection()
    assert result["model_available"], (
        f"Model '{OLLAMA_MODEL}' is not available locally. "
        f"Run: ollama pull {OLLAMA_MODEL}"
    )

