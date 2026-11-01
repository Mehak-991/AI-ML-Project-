"""API tests for datasets, training and prediction (SQLite-backed test DB)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.ml.synthetic import make_classification_frame, make_regression_frame
from app.schemas.common import ErrorResponse
from app.schemas.datasets import DatasetCreateResponse, DatasetValidationResponse
from app.schemas.models import ModelRead, PredictResponse
from tests.helpers import to_csv_bytes, to_xlsx_bytes

API = "/api/v1"


def upload(client: TestClient, content: bytes, filename: str = "data.csv", **form):
    return client.post(f"{API}/datasets", files={"file": (filename, content)}, data=form)


def error_code(response) -> str:
    return ErrorResponse.model_validate(response.json()).error.code


@pytest.fixture
def classification_dataset(api_client: TestClient) -> dict:
    response = upload(api_client, to_csv_bytes(make_classification_frame(200, seed=3)), name="demo")
    assert response.status_code == 201, response.text
    return response.json()["dataset"]


def test_full_training_to_prediction_workflow(api_client: TestClient, settings) -> None:
    created = upload(api_client, to_csv_bytes(make_classification_frame(200, seed=3)), name="demo")
    assert created.status_code == 201
    body = DatasetCreateResponse.model_validate(created.json())
    dataset_id = body.dataset.id
    assert body.dataset.name == "demo"
    assert body.dataset.n_rows == 205
    assert any(w.code == "duplicate_rows" for w in body.validation.warnings)
    assert len(list(settings.UPLOAD_DIR.iterdir())) == 1

    summary = api_client.get(
        f"{API}/datasets/{dataset_id}/summary", params={"target_column": "label"}
    )
    assert summary.status_code == 200
    assert DatasetValidationResponse.model_validate(summary.json()).validation.is_valid

    trained = api_client.post(
        f"{API}/models/train", json={"dataset_id": str(dataset_id), "target_column": "label"}
    )
    assert trained.status_code == 201, trained.text
    model = ModelRead.model_validate(trained.json())
    assert model.problem_type == "classification"
    assert model.metrics["test"]["accuracy"] > model.metrics["baseline_test"]["accuracy"]
    assert {f.name for f in model.feature_schema} == {"num_a", "num_b", "num_c", "cat_a", "cat_b"}
    assert "artifact_filename" not in trained.json()  # storage details are not exposed

    fetched = api_client.get(f"{API}/models/{model.id}")
    assert fetched.status_code == 200
    assert (
        api_client.get(f"{API}/models", params={"dataset_id": str(dataset_id)}).json()["total"] == 1
    )

    records = make_classification_frame(3, seed=99, n_duplicates=0).drop(columns="label")
    records = records.fillna({"num_a": 50.0, "cat_b": "small"}).to_dict("records")
    predicted = api_client.post(f"{API}/models/{model.id}/predict", json={"records": records})
    assert predicted.status_code == 200, predicted.text
    result = PredictResponse.model_validate(predicted.json())
    assert len(result.predictions) == 3
    assert set(result.predictions) <= {"yes", "no"}
    assert set(result.probabilities[0]) == {"no", "yes"}


def test_regression_workflow(api_client: TestClient) -> None:
    created = upload(api_client, to_xlsx_bytes(make_regression_frame(150, seed=4)), "reg.xlsx")
    assert created.status_code == 201, created.text
    dataset_id = created.json()["dataset"]["id"]
    trained = api_client.post(
        f"{API}/models/train",
        json={"dataset_id": dataset_id, "target_column": "value", "algorithm": "random_forest"},
    )
    assert trained.status_code == 201, trained.text
    model = trained.json()
    assert model["problem_type"] == "regression"
    assert "r2" in model["metrics"]["test"] and "accuracy" not in model["metrics"]["test"]

    record = {"num_a": 50.0, "num_b": 0.5, "num_c": 3, "cat_a": "red", "cat_b": None}
    predicted = api_client.post(
        f"{API}/models/{model['id']}/predict", json={"records": [record], "allow_missing": True}
    )
    assert predicted.status_code == 200, predicted.text
    assert isinstance(predicted.json()["predictions"][0], float)
    assert predicted.json()["probabilities"] is None


def test_validate_endpoint_does_not_persist(api_client: TestClient, settings) -> None:
    response = api_client.post(
        f"{API}/datasets/validate",
        files={"file": ("d.csv", to_csv_bytes(make_classification_frame(50)))},
        data={"target_column": "missing"},
    )
    assert response.status_code == 200
    body = DatasetValidationResponse.model_validate(response.json())
    assert not body.validation.is_valid
    assert body.validation.errors[0].code == "missing_target"
    assert body.summary.missing_values.total_missing_cells > 0
    assert api_client.get(f"{API}/datasets").json()["total"] == 0
    assert not settings.UPLOAD_DIR.exists() or not any(settings.UPLOAD_DIR.iterdir())


# --- error responses ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content", "status", "code"),
    [
        ("evil.exe", b"MZ...", 415, "unsupported_file_type"),
        ("data.csv", b"", 400, "invalid_file"),
        ("data.xlsx", b"not a zip", 400, "invalid_file"),
        ("data.csv", b"a,a\n1,2\n", 422, "data_validation_error"),
        ("data.csv", b"Unnamed: 0,b\n1,2\n", 422, "data_validation_error"),
    ],
)
def test_upload_errors(api_client: TestClient, settings, filename, content, status, code) -> None:
    response = upload(api_client, content, filename)
    assert response.status_code == status, response.text
    assert error_code(response) == code
    assert not settings.UPLOAD_DIR.exists() or not any(settings.UPLOAD_DIR.iterdir())


def test_upload_too_large(make_settings, session_factory) -> None:
    from app.api.deps import get_current_user, get_current_user_optional
    from app.database.models.user import User
    from app.database.session import get_db
    from app.main import create_app

    app = create_app(make_settings(APP_ENV="testing", MAX_UPLOAD_SIZE_MB=1))
    mock_admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin",
        hashed_password="mock",
        role="admin",
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: session_factory()
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_current_user_optional] = lambda: mock_admin
    with TestClient(app) as client:
        response = upload(client, b"a\n" + b"1\n" * 600_000)
    assert response.status_code == 413
    assert error_code(response) == "file_too_large"


def test_upload_requires_file(api_client: TestClient) -> None:
    response = api_client.post(f"{API}/datasets", data={"name": "x"})
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


def test_unknown_ids_return_404(api_client: TestClient) -> None:
    missing = uuid.uuid4()
    for response in (
        api_client.get(f"{API}/datasets/{missing}"),
        api_client.get(f"{API}/datasets/{missing}/summary"),
        api_client.get(f"{API}/models/{missing}"),
        api_client.post(f"{API}/models/{missing}/predict", json={"records": [{"a": 1}]}),
        api_client.post(
            f"{API}/models/train", json={"dataset_id": str(missing), "target_column": "x"}
        ),
    ):
        assert response.status_code == 404, response.text
        assert error_code(response) == "not_found"


def test_paths_are_not_accepted_as_ids(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/datasets/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (404, 422)
    response = api_client.post(
        f"{API}/models/train",
        json={"dataset_id": "../../etc/passwd", "target_column": "x"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        ({"target_column": "nope"}, 422, "training_error"),
        ({"target_column": "label", "problem_type": "regression"}, 422, "training_error"),
        ({"target_column": "label", "test_size": 0.9}, 422, "validation_error"),
        ({"target_column": "label", "feature_columns": ["label"]}, 422, "validation_error"),
        ({"target_column": "label", "dataset_path": "/etc/passwd"}, 422, "validation_error"),
    ],
)
def test_training_errors(api_client, classification_dataset, payload, status, code) -> None:
    response = api_client.post(
        f"{API}/models/train", json={"dataset_id": classification_dataset["id"]} | payload
    )
    assert response.status_code == status, response.text
    assert error_code(response) == code


def test_prediction_validation_errors(api_client, classification_dataset) -> None:
    model = api_client.post(
        f"{API}/models/train",
        json={"dataset_id": classification_dataset["id"], "target_column": "label"},
    ).json()
    url = f"{API}/models/{model['id']}/predict"
    good = {"num_a": 1.0, "num_b": 0.2, "num_c": 3, "cat_a": "red", "cat_b": "small"}

    response = api_client.post(url, json={"records": [good | {"num_a": "high", "extra": 1}]})
    assert response.status_code == 422
    details = ErrorResponse.model_validate(response.json()).error.details
    assert {d["field"] for d in details} == {"num_a", "extra"}

    response = api_client.post(url, json={"records": [good | {"cat_b": None}]})
    assert response.status_code == 422
    assert "Missing value" in response.json()["error"]["details"][0]["message"]

    response = api_client.post(url, json={"records": []})
    assert response.status_code == 422
    assert error_code(response) == "validation_error"

    response = api_client.post(
        url, json={"records": [{k: v for k, v in good.items() if k != "cat_a"}]}
    )
    assert response.json()["error"]["details"][0] == {
        "record": 0,
        "field": "cat_a",
        "message": "Feature is required.",
    }


def test_missing_artifact_returns_safe_500(api_client, classification_dataset, settings) -> None:
    model = api_client.post(
        f"{API}/models/train",
        json={"dataset_id": classification_dataset["id"], "target_column": "label"},
    ).json()
    for path in settings.MODEL_DIR.iterdir():
        path.unlink()
    good = {"num_a": 1.0, "num_b": 0.2, "num_c": 3, "cat_a": "red", "cat_b": "small"}
    response = api_client.post(f"{API}/models/{model['id']}/predict", json={"records": [good]})
    assert response.status_code == 500
    assert error_code(response) == "model_artifact_error"
    assert str(settings.MODEL_DIR) not in response.text


def test_database_not_configured_returns_503(client: TestClient, settings) -> None:
    from app.core import security

    token = security.create_access_token({"sub": str(uuid.uuid4())}, settings)
    response = client.get(f"{API}/datasets", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert error_code(response) == "database_not_configured"


def test_dataset_and_model_endpoints_require_authentication(client: TestClient) -> None:
    """Findings 1.3 & 1.4 verification: dataset and model read endpoints return 401 without bearer token."""
    random_id = uuid.uuid4()
    # Datasets (Finding 1.3)
    assert client.get(f"{API}/datasets").status_code == 401
    assert client.get(f"{API}/datasets/{random_id}").status_code == 401
    assert client.get(f"{API}/datasets/{random_id}/summary").status_code == 401
    # Models (Finding 1.4)
    assert client.get(f"{API}/models").status_code == 401
    assert client.get(f"{API}/models/{random_id}").status_code == 401


def test_openapi_documents_ml_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path, method in [
        (f"{API}/datasets", "post"),
        (f"{API}/datasets/validate", "post"),
        (f"{API}/datasets/{{dataset_id}}/summary", "get"),
        (f"{API}/models/train", "post"),
        (f"{API}/models/{{model_id}}", "get"),
        (f"{API}/models/{{model_id}}/predict", "post"),
    ]:
        assert method in paths[path], path
    components = schema["components"]["schemas"]
    assert {"TrainRequest", "PredictRequest", "PredictResponse", "ModelRead"} <= set(components)
