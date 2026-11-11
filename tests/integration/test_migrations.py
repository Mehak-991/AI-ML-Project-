"""Alembic migrations run end-to-end on a throwaway SQLite file.

PostgreSQL itself is exercised by tests/integration/test_database.py (needs
TEST_DATABASE_URL); this test checks revision ordering, the 0002 data backfill,
that the migrations match the ORM models exactly, and that downgrade works.
"""

import uuid
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.config import get_settings
from app.database.models import Base

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)  # no .env
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    yield config, url
    get_settings.cache_clear()


def _insert_model(conn, dataset_id: str, name: str, created_at: str) -> None:
    conn.execute(
        text(
            "INSERT INTO ml_models (id, name, dataset_id, problem_type, algorithm, target_column,"
            " feature_schema, metrics, training_metadata, artifact_filename, artifact_sha256,"
            " sklearn_version, created_at, updated_at) VALUES (:id, :name, :ds, 'regression',"
            " 'linear', 't', '[]', '{}', '{}', :file, :sha, '1.0', :ts, :ts)"
        ),
        {
            "id": uuid.uuid4().hex,
            "name": name,
            "ds": dataset_id,
            "file": f"{uuid.uuid4().hex}.joblib",
            "sha": "0" * 64,
            "ts": created_at,
        },
    )


def test_upgrade_backfill_check_and_downgrade(alembic_config) -> None:
    config, url = alembic_config
    command.upgrade(config, "0001")

    engine = create_engine(url)
    dataset_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO datasets (id, name, original_filename, stored_filename, file_format,"
                " size_bytes, sha256, n_rows, n_columns, columns, created_at, updated_at) VALUES"
                " (:id, 'd', 'd.csv', 'x.csv', 'csv', 1, :sha, 1, 1, '[]', :ts, :ts)"
            ),
            {"id": dataset_id, "sha": "0" * 64, "ts": "2026-01-01 00:00:00"},
        )
        _insert_model(conn, dataset_id, "churn", "2026-01-02 00:00:00")
        _insert_model(conn, dataset_id, "churn", "2026-01-03 00:00:00")
        _insert_model(conn, dataset_id, "other", "2026-01-04 00:00:00")

    command.upgrade(config, "head")
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, version FROM ml_models ORDER BY created_at")
        ).fetchall()
        assert [tuple(r) for r in rows] == [("churn", 1), ("churn", 2), ("other", 1)]
        # Migrations and ORM models must describe the same schema.
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []
    constraints = {c["name"] for c in inspect(engine).get_unique_constraints("ml_models")}
    assert "uq_ml_models_name_version" in constraints

    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    engine.dispose()
