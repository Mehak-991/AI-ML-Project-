"""Unit tests for Phase 13 Model Explainability (SHAP & LIME)."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.ml.synthetic import make_classification_frame, make_regression_frame
from tests.helpers import to_csv_bytes

API = "/api/v1"


@pytest.fixture
def trained_model_id(api_client: TestClient) -> str:
    # 1. Upload dataset
    upload_res = api_client.post(
        f"{API}/datasets",
        files={"file": ("explain_data.csv", to_csv_bytes(make_classification_frame(100, seed=15)))},
        data={"name": "explain_dataset"},
    )
    assert upload_res.status_code == 201
    dataset_id = upload_res.json()["dataset"]["id"]

    # 2. Train model
    train_res = api_client.post(
        f"{API}/models/train",
        json={"dataset_id": dataset_id, "target_column": "label", "algorithm": "random_forest"},
    )
    assert train_res.status_code == 201
    return train_res.json()["id"]


def test_explainability_summary_endpoint(api_client: TestClient, trained_model_id: str) -> None:
    res = api_client.get(f"{API}/models/{trained_model_id}/explainability/summary")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["model_id"] == trained_model_id
    assert "shap" in data["supported_explainers"]
    assert len(data["feature_names"]) > 0


def test_global_feature_importance_endpoint(api_client: TestClient, trained_model_id: str) -> None:
    res = api_client.get(f"{API}/models/{trained_model_id}/explainability/feature-importance?sample_size=20")
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data["feature_importances"]) > 0
    assert data["feature_importances"][0]["rank"] == 1
    assert data["computation_time_seconds"] >= 0


def test_local_shap_explanation_endpoint(api_client: TestClient, trained_model_id: str) -> None:
    sample_record = {"num_a": 12.5, "num_b": 0.45, "num_c": 100.0, "cat_a": "medium", "cat_b": "low"}
    res = api_client.post(
        f"{API}/models/{trained_model_id}/explainability/shap",
        json={"record": sample_record, "num_features": 5, "background_samples": 20},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert "prediction" in data
    assert "feature_contributions" in data
    assert "disclaimer" in data
    assert len(data["feature_contributions"]) <= 5
