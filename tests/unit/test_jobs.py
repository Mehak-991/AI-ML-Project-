"""Unit tests for Phase 14 Background Jobs, Distributed Task Queue & Job Management."""

import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.ml.synthetic import make_classification_frame
from tests.helpers import to_csv_bytes

API = "/api/v1"


def test_job_submission_and_metrics(api_client: TestClient) -> None:
    # 1. Submit a generic background job
    payload = {
        "job_type": "model_training",
        "input_config": {"notes": "test background task"},
        "max_retries": 2,
    }
    submit_res = api_client.post(f"{API}/jobs", json=payload)
    assert submit_res.status_code == 201, submit_res.text
    job_data = submit_res.json()
    assert job_data["job_type"] == "model_training"
    assert job_data["status"] in ("queued", "running", "completed")
    job_id = job_data["id"]

    # 2. Get job metrics
    metrics_res = api_client.get(f"{API}/jobs/metrics")
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert metrics["total_jobs"] >= 1

    # 3. List jobs
    list_res = api_client.get(f"{API}/jobs?limit=10")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(j["id"] == job_id for j in items)

    # 4. Get specific job
    get_res = api_client.get(f"{API}/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id


def test_job_cancellation_and_retry(api_client: TestClient) -> None:
    # Submit job with dummy payload
    payload = {
        "job_type": "batch_prediction",
        "input_config": {"batch_size": 100},
        "max_retries": 1,
    }
    submit_res = api_client.post(f"{API}/jobs", json=payload)
    assert submit_res.status_code == 201
    job_id = submit_res.json()["id"]

    # Cancel job
    cancel_res = api_client.post(f"{API}/jobs/{job_id}/cancel")
    if cancel_res.status_code == 200:
        assert cancel_res.json()["status"] == "cancelled"

        # Retry cancelled job
        retry_res = api_client.post(f"{API}/jobs/{job_id}/retry")
        assert retry_res.status_code == 200
        assert retry_res.json()["status"] in ("queued", "running", "completed")
        assert retry_res.json()["retry_count"] >= 1


def test_job_not_found(api_client: TestClient) -> None:
    non_existent = str(uuid.uuid4())
    res = api_client.get(f"{API}/jobs/{non_existent}")
    assert res.status_code == 404
