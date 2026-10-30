"""Unit tests for Phase 12 Automated ML Pipelines and Experiment Tracking."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.ml.synthetic import make_classification_frame, make_regression_frame
from tests.helpers import to_csv_bytes

API = "/api/v1"


def test_experiment_lifecycle_and_pipeline_execution(api_client: TestClient) -> None:
    # 1. Upload dataset
    upload_res = api_client.post(
        f"{API}/datasets",
        files={"file": ("exp_data.csv", to_csv_bytes(make_classification_frame(150, seed=42)))},
        data={"name": "exp_dataset"},
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["dataset"]["id"]

    # 2. Create Experiment
    exp_payload = {
        "name": "rf_experiment_test",
        "description": "GridSearchCV random forest test",
        "dataset_id": dataset_id,
        "target_column": "label",
        "problem_type": "classification",
        "algorithm": "random_forest",
        "search_strategy": "grid",
        "hyperparameter_config": {"n_estimators": [10, 20], "max_depth": [3, 5]},
        "cv_folds": 2,
        "test_size": 0.2,
        "validation_size": 0.1,
        "random_state": 42,
    }
    create_res = api_client.post(f"{API}/experiments", json=exp_payload)
    assert create_res.status_code == 201, create_res.text
    exp_data = create_res.json()
    exp_id = exp_data["id"]
    assert exp_data["status"] == "pending"

    # 3. List Experiments
    list_res = api_client.get(f"{API}/experiments")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1

    # 4. Execute Pipeline Run (Automated ML)
    run_res = api_client.post(f"{API}/experiments/{exp_id}/run")
    assert run_res.status_code == 200, run_res.text
    run_data = run_res.json()
    assert run_data["status"] == "completed"
    assert "accuracy" in run_data["test_metrics"]
    assert run_data["registered_model_id"] is not None

    # 5. Verify registered model exists in ML registry
    model_res = api_client.get(f"{API}/models/{run_data['registered_model_id']}")
    assert model_res.status_code == 200
    assert model_res.json()["name"] == "rf_experiment_test"

    # 6. Compare Experiments
    compare_res = api_client.get(f"{API}/experiments/compare?experiment_ids={exp_id}")
    assert compare_res.status_code == 200
    comp_data = compare_res.json()
    assert len(comp_data["experiments"]) == 1
    assert comp_data["experiments"][0]["experiment_name"] == "rf_experiment_test"
