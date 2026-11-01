"""PostgreSQL integration tests.

REQUIRES a real, **disposable** PostgreSQL database:
    TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/aiproject_test \
        pytest -m integration

Everything runs inside an outer transaction that is rolled back, so no tables
or rows are left behind (PostgreSQL supports transactional DDL).
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import Base
from app.database.session import get_db
from app.main import create_app
from app.ml.synthetic import make_classification_frame
from tests.helpers import to_csv_bytes

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def pg_connection() -> Iterator:
    engine = create_engine(TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))
    with engine.connect() as connection:
        transaction = connection.begin()
        Base.metadata.create_all(connection)
        yield connection
        transaction.rollback()
    engine.dispose()


@requires_db
def test_readiness_against_real_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["components"]["database"] == "ok"


@requires_db
def test_schema_uses_postgres_types(pg_connection) -> None:
    columns = {c["name"]: c for c in inspect(pg_connection).get_columns("datasets")}
    assert type(columns["columns"]["type"]).__name__ == "JSONB"
    assert type(columns["id"]["type"]).__name__ == "UUID"


@requires_db
def test_api_workflow_against_postgres(pg_connection, make_settings) -> None:
    app = create_app(make_settings(APP_ENV="testing"))

    def _get_db() -> Iterator[Session]:
        with Session(bind=pg_connection, join_transaction_mode="create_savepoint") as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as client:
        # Dataset upload and training require an authenticated admin/ML engineer. On a
        # fresh disposable database the first registered user is the bootstrap admin.
        credentials = {"email": "pg-admin@example.com", "password": "Password123!"}
        assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
        login = client.post("/api/v1/auth/login", json=credentials).json()
        client.headers["Authorization"] = f"Bearer {login['access_token']}"

        created = client.post(
            "/api/v1/datasets",
            files={"file": ("d.csv", to_csv_bytes(make_classification_frame(120, seed=1)))},
        )
        assert created.status_code == 201, created.text
        dataset_id = created.json()["dataset"]["id"]
        trained = client.post(
            "/api/v1/models/train", json={"dataset_id": dataset_id, "target_column": "label"}
        )
        assert trained.status_code == 201, trained.text
        assert client.get("/api/v1/models").json()["total"] >= 1

        model_id = trained.json()["id"]
        record = {"num_a": 1.0, "num_b": 0.2, "num_c": 3, "cat_a": "red", "cat_b": "small"}
        predicted = client.post(f"/api/v1/models/{model_id}/predict", json={"records": [record]})
        assert predicted.status_code == 200, predicted.text
        history = client.get("/api/v1/predictions/history", params={"model_id": model_id})
        assert history.json()["total"] == 1
