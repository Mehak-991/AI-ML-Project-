import uuid
import pytest
from fastapi.testclient import TestClient

from app.database.models.ml_model import MLModel
from app.ml.persistence import save_artifact


import hashlib
import sklearn

def _create_test_model(session, tmp_path, settings) -> MLModel:
    filename = f"{uuid.uuid4().hex}.joblib"
    fake_payload = {"pipeline": "fake_pipeline"}
    path = tmp_path / filename
    import joblib
    joblib.dump(fake_payload, path)

    digest = hashlib.sha256()
    with path.open("rb") as f:
        digest.update(f.read())
    sha = digest.hexdigest()

    model = MLModel(
        name="test-churn",
        version=1,
        dataset_id=uuid.uuid4(),
        problem_type="classification",
        algorithm="linear",
        target_column="churn",
        feature_schema=[{"name": "tenure", "kind": "numeric"}],
        metrics={"test": {"accuracy": 0.95}},
        training_metadata={"trained_at": "2026-10-30T10:00:00Z", "training_seconds": 1.2},
        artifact_filename=filename,
        artifact_sha256=sha,
        sklearn_version=sklearn.__version__,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def test_deploy_and_undeploy_flow(api_client: TestClient, db_session, settings, tmp_path):
    # Set model dir to tmp
    settings.MODEL_DIR = tmp_path
    model = _create_test_model(db_session, tmp_path, settings)

    # 1. Deploy model
    deploy_res = api_client.post(
        f"/api/v1/models/{model.id}/deploy",
        json={"environment": "production", "configuration": {"replicas": 2}},
    )
    assert deploy_res.status_code == 200
    dep_data = deploy_res.json()
    assert dep_data["status"] == "Deployed"
    assert dep_data["model_id"] == str(model.id)
    assert dep_data["version"] == 1

    # 2. List deployments
    list_res = api_client.get(f"/api/v1/deployments?model_id={model.id}")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1

    # 3. Undeploy model
    undep_res = api_client.post(f"/api/v1/models/{model.id}/undeploy")
    assert undep_res.status_code == 200
    assert undep_res.json()["status"] == "Undeployed"

    # 4. Monitoring overview check
    mon_res = api_client.get("/api/v1/monitoring/overview")
    assert mon_res.status_code == 200
    mon_data = mon_res.json()
    assert mon_data["total_deployments"] >= 1


def test_prediction_history_and_ground_truth(api_client: TestClient, db_session):
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
    res = api_client.get(f"/api/v1/predictions/history?model_id={test_model_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(log.id)

    # Submit ground truth
    gt_res = api_client.post(
        f"/api/v1/predictions/history/{log.id}/ground-truth",
        json={"ground_truth": [0, 1]},
    )
    assert gt_res.status_code == 200
    assert gt_res.json()["is_evaluated"] is True
