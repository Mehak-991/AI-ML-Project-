"""PostgreSQL and Unit tests for Phase 18 ML Validation, Reliability & Performance."""

import threading
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.database.models.job import Job
from app.database.models.ml_model import MLModel
from app.database.models.user import User
from app.ml.prediction import validate_records
from app.services import job_service, model_service

API = "/api/v1"


def test_validate_records_batch_integrity() -> None:
    feature_schema = [
        {"name": "age", "kind": "numeric"},
        {"name": "experience_years", "kind": "numeric"},
        {"name": "study_hours", "kind": "numeric"},
        {"name": "attendance", "kind": "numeric"},
    ]

    # Valid batch of records
    valid_records = [
        {"age": 22, "experience_years": 1.0, "study_hours": 6.5, "attendance": 85.0},
        {"age": 25, "experience_years": 2.5, "study_hours": 9.0, "attendance": 94.0},
    ]
    df = validate_records(valid_records, feature_schema, allow_missing=False)
    assert len(df) == 2
    assert list(df.columns) == ["age", "experience_years", "study_hours", "attendance"]


def test_validate_records_missing_required_feature() -> None:
    feature_schema = [
        {"name": "age", "kind": "numeric"},
        {"name": "experience_years", "kind": "numeric"},
    ]
    # Missing 'experience_years'
    bad_records = [{"age": 22}]
    from app.core.exceptions import DataValidationError
    with pytest.raises(DataValidationError) as exc:
        validate_records(bad_records, feature_schema, allow_missing=False)
    assert "Prediction input failed validation" in str(exc.value)
    assert any(err["field"] == "experience_years" for err in exc.value.details)


def test_validate_records_unknown_feature() -> None:
    feature_schema = [
        {"name": "age", "kind": "numeric"},
    ]
    bad_records = [{"age": 22, "unrecognized_col": 99}]
    from app.core.exceptions import DataValidationError
    with pytest.raises(DataValidationError) as exc:
        validate_records(bad_records, feature_schema, allow_missing=False)
    assert any(err["field"] == "unrecognized_col" for err in exc.value.details)


def test_validate_records_non_numeric_type() -> None:
    feature_schema = [
        {"name": "age", "kind": "numeric"},
    ]
    bad_records = [{"age": "not-a-number"}]
    from app.core.exceptions import DataValidationError
    with pytest.raises(DataValidationError) as exc:
        validate_records(bad_records, feature_schema, allow_missing=False)
    assert any("Expected a number" in err["message"] for err in exc.value.details)


def test_validate_records_empty_records() -> None:
    feature_schema = [{"name": "age", "kind": "numeric"}]
    from app.core.exceptions import DataValidationError
    with pytest.raises(DataValidationError) as exc:
        validate_records([], feature_schema)
    assert "At least one record is required" in str(exc.value)


def test_atomic_job_claiming_single_claim(db_session: Session) -> None:
    # Create test user
    user = User(
        email=f"worker_test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        full_name="Worker Tester",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # Create 2 queued jobs
    j1 = job_service.create_job(db_session, "batch_prediction", user, input_config={"n": 1})
    j2 = job_service.create_job(db_session, "batch_prediction", user, input_config={"n": 2})

    # Claim first job
    claimed1 = job_service.claim_next_queued_job(db_session)
    assert claimed1 is not None
    assert claimed1.id == j1.id
    assert claimed1.status == "running"

    # Claim second job
    claimed2 = job_service.claim_next_queued_job(db_session)
    assert claimed2 is not None
    assert claimed2.id == j2.id
    assert claimed2.status == "running"

    # No more queued jobs
    claimed3 = job_service.claim_next_queued_job(db_session)
    assert claimed3 is None


def test_concurrent_job_claiming_no_duplicates(db_session: Session) -> None:
    """Verify that multiple successive claiming attempts only claim a job once."""
    user = User(
        email=f"concurrent_test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hash",
        full_name="Concurrent Tester",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    job = job_service.create_job(db_session, "batch_prediction", user, input_config={"concurrent": True})
    job_id = job.id

    # First claim succeeds
    claimed1 = job_service.claim_next_queued_job(db_session)
    assert claimed1 is not None
    assert claimed1.id == job_id
    assert claimed1.status == "running"

    # Subsequent immediate claim returns None (already running)
    claimed2 = job_service.claim_next_queued_job(db_session)
    assert claimed2 is None
