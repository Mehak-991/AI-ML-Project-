import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.schemas.common import ErrorResponse


@pytest.fixture
def error_client(app: FastAPI) -> TestClient:
    @app.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("secret internal detail: password=hunter2")

    @app.get("/_test/not-found")
    def not_found() -> None:
        raise NotFoundError("Model 'abc' was not found.")

    @app.get("/_test/unavailable")
    def unavailable() -> None:
        raise ServiceUnavailableError()

    @app.get("/_test/http")
    def http_error() -> None:
        raise HTTPException(status_code=403, detail="Forbidden here")

    @app.get("/_test/items/{item_id}")
    def item(item_id: int) -> dict:
        return {"id": item_id}

    return TestClient(app, raise_server_exceptions=False)


def _error(response) -> ErrorResponse:
    return ErrorResponse.model_validate(response.json())


def test_unhandled_exception_returns_generic_500(error_client: TestClient) -> None:
    response = error_client.get("/_test/crash")
    assert response.status_code == 500
    error = _error(response).error
    assert error.code == "internal_server_error"
    assert error.message == "An unexpected error occurred."
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


def test_app_error_uses_its_status_and_code(error_client: TestClient) -> None:
    response = error_client.get("/_test/not-found")
    assert response.status_code == 404
    error = _error(response).error
    assert error.code == "not_found"
    assert error.message == "Model 'abc' was not found."

    response = error_client.get("/_test/unavailable")
    assert response.status_code == 503
    assert _error(response).error.code == "service_unavailable"


def test_http_exception_is_wrapped(error_client: TestClient) -> None:
    response = error_client.get("/_test/http")
    assert response.status_code == 403
    error = _error(response).error
    assert error.code == "forbidden"
    assert error.message == "Forbidden here"


def test_unknown_route_returns_404_envelope(error_client: TestClient) -> None:
    response = error_client.get("/does-not-exist")
    assert response.status_code == 404
    assert _error(response).error.code == "not_found"


def test_method_not_allowed(error_client: TestClient) -> None:
    response = error_client.post("/health")
    assert response.status_code == 405
    assert _error(response).error.code == "method_not_allowed"


def test_validation_error_hides_input(error_client: TestClient) -> None:
    response = error_client.get("/_test/items/not-a-number-secret")
    assert response.status_code == 422
    error = _error(response).error
    assert error.code == "validation_error"
    assert error.details[0]["loc"] == ["path", "item_id"]
    assert "not-a-number-secret" not in response.text
