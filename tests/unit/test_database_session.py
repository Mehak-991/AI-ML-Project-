"""Session, diagnostics and repository behaviour.

Uses SQLite as a stand-in for PostgreSQL; PostgreSQL-specific behaviour is
covered by tests/integration/test_database.py (requires TEST_DATABASE_URL).
"""

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError
from app.database import session as db_session
from app.database.base import Base
from app.database.models import Dataset, MLModel
from app.repositories.datasets import DatasetRepository
from app.repositories.ml_models import MLModelRepository


def _use_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()


def test_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    with pytest.raises(DatabaseNotConfiguredError):
        db_session.get_engine()
    with pytest.raises(DatabaseNotConfiguredError):
        next(db_session.get_db())


def test_engine_is_reused_and_disposed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _use_sqlite(monkeypatch, tmp_path)
    engine = db_session.get_engine()
    assert db_session.get_engine() is engine
    db_session.dispose_engine()
    assert db_session.get_engine() is not engine


def test_get_db_closes_session(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _use_sqlite(monkeypatch, tmp_path)
    fake = MagicMock()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: lambda: fake)
    generator = db_session.get_db()
    assert next(generator) is fake
    generator.close()
    fake.close.assert_called_once()
    fake.rollback.assert_not_called()


def test_get_db_rolls_back_on_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _use_sqlite(monkeypatch, tmp_path)
    fake = MagicMock()
    monkeypatch.setattr(db_session, "get_session_factory", lambda: lambda: fake)
    generator = db_session.get_db()
    next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("boom"))
    fake.rollback.assert_called_once()
    fake.close.assert_called_once()


def test_diagnose_not_configured(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    result = db_session.diagnose_database()
    assert (result.ok, result.category) == (False, "not_configured")


def test_diagnose_success_with_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _use_sqlite(monkeypatch, tmp_path)
    result = db_session.diagnose_database()
    assert result.ok and result.category == "ok"
    assert result.latency_ms is not None
    assert db_session.check_database_connection() is True


def test_diagnose_failure_hides_password(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:s3cret-pw@db.example:5432/app")
    get_settings.cache_clear()

    def refuse():
        raise OperationalError("connect", {}, Exception("Connection refused"))

    fake_engine = MagicMock()
    fake_engine.connect.side_effect = refuse
    monkeypatch.setattr(db_session, "get_engine", lambda: fake_engine)

    result = db_session.diagnose_database()
    assert (result.ok, result.category) == (False, "connection_refused")
    assert "s3cret-pw" not in repr(result)
    assert result.url.startswith("postgresql+psycopg://app:***@db.example")


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ('FATAL: password authentication failed for user "app"', "authentication_failed"),
        ('FATAL: database "nope" does not exist', "database_not_found"),
        ('could not translate host name "x" to address', "host_not_found"),
        ("timeout expired", "timeout"),
        ("something odd", "unknown_error"),
    ],
)
def test_classify_database_error(message: str, category: str) -> None:
    assert db_session.classify_database_error(Exception(message))[0] == category


def test_metadata_has_naming_convention() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert {"datasets", "ml_models"} <= set(Base.metadata.tables)


def _dataset(**overrides) -> Dataset:
    values = {
        "name": "d",
        "original_filename": "d.csv",
        "stored_filename": f"{uuid.uuid4().hex}.csv",
        "file_format": "csv",
        "size_bytes": 10,
        "sha256": "a" * 64,
        "n_rows": 2,
        "n_columns": 2,
        "columns": [{"name": "a", "dtype": "int64", "kind": "numeric"}],
    }
    return Dataset(**(values | overrides))


def test_repositories_roundtrip(db_session) -> None:
    datasets = DatasetRepository(db_session)
    first = datasets.add(_dataset(name="first"))
    datasets.add(_dataset(name="second", sha256="b" * 64))
    db_session.commit()

    assert datasets.count() == 2
    assert datasets.get(first.id).columns[0]["kind"] == "numeric"
    assert datasets.get_by_sha256("b" * 64).name == "second"
    assert len(datasets.list(limit=1)) == 1
    assert datasets.get(uuid.uuid4()) is None

    models = MLModelRepository(db_session)
    models.add(
        MLModel(
            name="m",
            dataset_id=first.id,
            problem_type="classification",
            algorithm="linear",
            target_column="a",
            feature_schema=[],
            metrics={"test": {"accuracy": 1.0}},
            training_metadata={},
            artifact_filename=f"{uuid.uuid4().hex}.joblib",
            artifact_sha256="c" * 64,
            sklearn_version="1.0",
        )
    )
    db_session.commit()
    assert [m.name for m in models.list_for_dataset(first.id)] == ["m"]
    assert models.list_for_dataset(uuid.uuid4()) == []


def test_session_rollback_discards_changes(db_session) -> None:
    repo = DatasetRepository(db_session)
    repo.add(_dataset())
    db_session.rollback()
    assert repo.count() == 0
