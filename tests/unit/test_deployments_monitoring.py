import uuid
import pytest
from fastapi.testclient import TestClient

from app.schemas.datasets import DatasetCreateResponse
from app.schemas.models import ModelRead
from tests.helpers import to_csv_bytes
from app.ml.synthetic import make_classification_frame


API = "/api/v1"


def test_deploy_and_undeploy_workflow(api_client: TestClient) -> None:
    # 1. Create dataset and train a real model
    upload_res = api_client.post(
        f"{API}/datasets",
        files={"file": ("test_data.csv", to_csv_bytes(make_classification_frame(100, seed=12)))},
        data={"name": "test_dataset"},
    )
    assert upload_res.status_code == 201
    dataset = DatasetCreateResponse.model_validate(upload_res.json()).dataset

    trained = api_client.post(
        f"{API}/models/train", json={"dataset_id": str(dataset.id), "target_column": "label"}
    )
    assert trained.status_code == 201
    model = ModelRead.model_validate(trained.json())

    # 2. Deploy model
    deploy_res = api_client.post(
        f"{API}/models/{model.id}/deploy",
        json={"environment": "production", "configuration": {"replicas": 2}},
    )
    assert deploy_res.status_code == 200, deploy_res.text
    dep_data = deploy_res.json()
    assert dep_data["status"] == "Deployed"
    assert dep_data["model_id"] == str(model.id)
    assert dep_data["version"] == 1

    # 3. List deployments
    list_res = api_client.get(f"{API}/deployments?model_id={model.id}")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1

    # 4. Undeploy model
    undep_res = api_client.post(f"{API}/models/{model.id}/undeploy")
    assert undep_res.status_code == 200
    assert undep_res.json()["status"] == "Undeployed"

    # 5. Monitoring overview check
    mon_res = api_client.get(f"{API}/monitoring/overview")
    assert mon_res.status_code == 200
    mon_data = mon_res.json()
    assert mon_data["total_deployments"] >= 1


def test_prediction_history_and_ground_truth(api_client: TestClient, db_session) -> None:
    from app.services import deployment_service
    test_model_id = uuid.uuid4()

    # Log a prediction directly
    log = deployment_service.log_prediction(
        db_session,
        model_id=test_model_id,
        deployment_id=None,
        record_count=2,
        duration_ms=45.2,
        status="success",
        problem_type="classification",
        prediction_summary={"count": 2, "predictions": [0, 1]},
    )
    assert log is not None

    # Fetch via API
    res = api_client.get(f"{API}/predictions/history?model_id={test_model_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(log.id)

    # Submit ground truth
    gt_res = api_client.post(
        f"{API}/predictions/history/{log.id}/ground-truth",
        json={"ground_truth": [0, 1]},
    )
    assert gt_res.status_code == 200
    assert gt_res.json()["is_evaluated"] is True
