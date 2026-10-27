"""Request IDs, structured logs, security headers, body limits, rate limits,
database failure mapping, model versioning and compatibility handling."""

import json
import logging
from unittest.mock import MagicMock

import joblib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.middleware import RateLimitMiddleware, TokenBucketLimiter
from app.database.session import get_db
from app.main import create_app
from app.ml.synthetic import make_classification_frame
from app.utils.logging import JsonFormatter, RequestIdFilter, request_id_var
from tests.helpers import to_csv_bytes

API = "/api/v1"


def code(response) -> str:
    return response.json()["error"]["code"]


# --- request IDs, headers, docs --------------------------------------------------------


def test_request_id_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    assert client.get("/health").headers["x-request-id"] != request_id


@pytest.mark.parametrize(
    ("incoming", "kept"),
    [
        ("abc-123.DEF_4", True),
        ("bad id with spaces", False),
        ("x" * 65, False),
        ("<script>", False),
    ],
)
def test_incoming_request_id_validated(client: TestClient, incoming: str, kept: bool) -> None:
    echoed = client.get("/health", headers={"X-Request-ID": incoming}).headers["x-request-id"]
    assert (echoed == incoming) is kept


def test_request_id_visible_inside_sync_handlers(app: FastAPI) -> None:
    @app.get("/_test/rid")
    def rid() -> dict:
        return {"request_id": request_id_var.get()}

    with TestClient(app) as client:
        response = client.get("/_test/rid", headers={"X-Request-ID": "trace-1"})
    assert response.json() == {"request_id": "trace-1"}


def test_security_headers(client: TestClient) -> None:
    headers = client.get(f"{API}/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"
    assert "cache-control" not in client.get("/docs").headers


def test_docs_can_be_disabled(make_settings) -> None:
    with TestClient(create_app(make_settings(DOCS_ENABLED=False))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").status_code == 200


# --- structured logging ---------------------------------------------------------------


def test_access_log_has_structured_fields_without_query(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.access")
    client.get("/health?token=secret-value", headers={"X-Request-ID": "req-42"})
    record = next(r for r in caplog.records if r.name == "app.access")
    assert (record.http_method, record.path, record.status) == ("GET", "/health", 200)
    assert record.duration_ms >= 0
    # Only the server's own logs matter (the test HTTP client logs its URL itself).
    app_records = [r for r in caplog.records if r.name.startswith("app")]
    assert all("secret-value" not in r.getMessage() for r in app_records)


def test_json_formatter_emits_one_object_with_request_id_and_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "app.access", "levelname": "INFO", "msg": "GET %s", "args": ("/x",)}
    )
    record.status = 201
    token = request_id_var.set("rid-7")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "GET /x"
    assert payload["request_id"] == "rid-7"
    assert payload["status"] == 201
    assert payload["level"] == "INFO"


# --- request size limits ----------------------------------------------------------------


def test_json_body_over_limit_rejected_by_content_length(make_settings) -> None:
    app = create_app(make_settings(MAX_REQUEST_BODY_MB=0.001))  # ~1 KB
    with TestClient(app) as client:
        response = client.post(f"{API}/tokens/count", json={"text": "x" * 5000})
    assert response.status_code == 413
    assert code(response) == "request_too_large"
    assert response.headers["x-request-id"]


def test_chunked_body_over_limit_rejected_while_streaming(make_settings) -> None:
    app = create_app(make_settings(MAX_REQUEST_BODY_MB=0.001))

    def chunks():
        yield b'{"text": "'
        for _ in range(20):
            yield b"x" * 200
        yield b'"}'

    with TestClient(app) as client:
        response = client.post(
            f"{API}/tokens/count", content=chunks(), headers={"Content-Type": "application/json"}
        )
    assert response.status_code == 413
    assert code(response) == "request_too_large"


def test_invalid_content_length(client: TestClient) -> None:
    response = client.post(f"{API}/tokens/count", content=b"{}", headers={"Content-Length": "abc"})
    assert response.status_code == 400


def test_uploads_get_the_larger_upload_limit(make_settings, session_factory) -> None:
    """A ~10 KB CSV passes even though plain JSON bodies are capped at ~1 KB."""
    app = create_app(make_settings(MAX_REQUEST_BODY_MB=0.001, MAX_UPLOAD_SIZE_MB=1))
    app.dependency_overrides[get_db] = lambda: session_factory()
    with TestClient(app) as client:
        response = client.post(
            f"{API}/datasets/validate",
            files={"file": ("d.csv", to_csv_bytes(make_classification_frame(200)))},
        )
    assert response.status_code == 200, response.text


# --- rate limiting -----------------------------------------------------------------------


def test_token_bucket_refills_over_time() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(clock=lambda: now[0])
    assert [limiter.acquire("k", 2)[0] for _ in range(3)] == [True, True, False]
    allowed, retry_after = limiter.acquire("k", 2)
    assert not allowed and retry_after == 30  # 2/min = one token every 30 s
    now[0] += 30
    assert limiter.acquire("k", 2)[0] is True
    assert limiter.acquire("other-client", 2)[0] is True  # independent key


def test_token_bucket_prunes_keys() -> None:
    limiter = TokenBucketLimiter(max_keys=10)
    for i in range(50):
        limiter.acquire(f"client-{i}", 5)
    assert len(limiter._buckets) <= 10


def test_rate_limit_returns_429_with_retry_after(make_settings) -> None:
    app = create_app(make_settings(RATE_LIMIT_AI_PER_MINUTE=2))
    body = {"messages": [{"role": "user", "content": "hi"}]}
    with TestClient(app) as client:
        statuses = [client.post(f"{API}/llm/chat", json=body).status_code for _ in range(3)]
        limited = client.post(f"{API}/llm/chat", json=body)
        # Other buckets and health checks are unaffected.
        assert client.post(f"{API}/tokens/count", json={"text": "a"}).status_code == 200
        assert all(client.get("/health").status_code == 200 for _ in range(5))
    assert statuses == [503, 503, 429]  # 503 = no API key configured, but still counted
    assert limited.status_code == 429
    assert code(limited) == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["x-ratelimit-limit"] == "2"


def test_rate_limit_rules() -> None:
    middleware = RateLimitMiddleware(
        MagicMock(),
        api_prefix=API,
        default_per_minute=100,
        ai_per_minute=10,
        training_per_minute=5,
    )
    assert middleware.rule_for("GET", "/health") is None
    assert middleware.rule_for("OPTIONS", f"{API}/llm/chat") is None
    assert middleware.rule_for("POST", f"{API}/embeddings").name == "ai"
    assert middleware.rule_for("POST", f"{API}/nlp/analyze").name == "ai"
    assert middleware.rule_for("POST", f"{API}/models/train").name == "training"
    assert middleware.rule_for("POST", f"{API}/datasets").name == "training"
    assert middleware.rule_for("GET", f"{API}/datasets").name == "default"


def test_rate_limiting_can_be_disabled(make_settings) -> None:
    app = create_app(make_settings(RATE_LIMIT_ENABLED=False, RATE_LIMIT_AI_PER_MINUTE=1))
    with TestClient(app) as client:
        body = {"messages": [{"role": "user", "content": "x"}]}
        assert all(client.post(f"{API}/llm/chat", json=body).status_code == 503 for _ in range(3))


# --- database failures ---------------------------------------------------------------------


def _failing_session(exc: Exception):
    session = MagicMock()
    session.scalars.side_effect = exc
    session.scalar.side_effect = exc
    session.get.side_effect = exc
    return session


@pytest.mark.parametrize(
    ("exc", "status", "error_code"),
    [
        (
            OperationalError(
                "SELECT", {}, Exception('connection to server at "db.internal" failed')
            ),
            503,
            "database_unavailable",
        ),
        (IntegrityError("INSERT", {}, Exception("duplicate key")), 409, "conflict"),
    ],
)
def test_database_errors_are_mapped_without_leaking(app, exc, status, error_code) -> None:
    app.dependency_overrides[get_db] = lambda: _failing_session(exc)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"{API}/datasets")
    assert response.status_code == status
    assert code(response) == error_code
    assert "db.internal" not in response.text
    assert "duplicate key" not in response.text


# --- model versioning and compatibility ------------------------------------------------------


@pytest.fixture
def trained_model(api_client) -> dict:
    dataset = api_client.post(
        f"{API}/datasets", files={"file": ("d.csv", to_csv_bytes(make_classification_frame(120)))}
    ).json()["dataset"]
    payload = {"dataset_id": dataset["id"], "target_column": "label", "name": "demo-model"}
    first = api_client.post(f"{API}/models/train", json=payload)
    assert first.status_code == 201, first.text
    return {"payload": payload, "model": first.json()}


GOOD_RECORD = {"num_a": 1.0, "num_b": 0.2, "num_c": 3, "cat_a": "red", "cat_b": "small"}


def test_retraining_same_name_increments_version(api_client, trained_model) -> None:
    assert trained_model["model"]["version"] == 1
    second = api_client.post(f"{API}/models/train", json=trained_model["payload"]).json()
    other = api_client.post(
        f"{API}/models/train", json=trained_model["payload"] | {"name": "another"}
    ).json()
    assert second["version"] == 2
    assert second["id"] != trained_model["model"]["id"]
    assert other["version"] == 1


def _set_sklearn_version(session_factory, model_id: str, version: str) -> None:
    from app.database.models import MLModel

    with session_factory() as session:
        import uuid

        session.get(MLModel, uuid.UUID(model_id)).sklearn_version = version
        session.commit()


def test_incompatible_sklearn_version_refused_before_unpickling(
    api_client, trained_model, session_factory, monkeypatch
) -> None:
    from app.ml import persistence

    loads = []
    monkeypatch.setattr(persistence, "load_artifact", lambda *a, **k: loads.append(1))
    model_id = trained_model["model"]["id"]
    _set_sklearn_version(session_factory, model_id, "0.24.2")
    response = api_client.post(f"{API}/models/{model_id}/predict", json={"records": [GOOD_RECORD]})
    assert response.status_code == 409
    assert code(response) == "model_incompatible"
    assert response.json()["error"]["details"]["trained_with"] == "0.24.2"
    assert loads == []  # never unpickled


def test_patch_version_difference_is_accepted(api_client, trained_model, session_factory) -> None:
    import sklearn

    major, minor = sklearn.__version__.split(".")[:2]
    _set_sklearn_version(session_factory, trained_model["model"]["id"], f"{major}.{minor}.999")
    url = f"{API}/models/{trained_model['model']['id']}/predict"
    assert api_client.post(url, json={"records": [GOOD_RECORD]}).status_code == 200


def test_warn_policy_loads_anyway(make_settings, session_factory) -> None:
    from app.ml.persistence import check_sklearn_compatibility

    check_sklearn_compatibility("0.24.2", "warn")  # no exception


def _rewrite_artifact(settings, session_factory, model_id: str, payload) -> None:
    import uuid

    from app.database.models import MLModel
    from app.ml.persistence import file_sha256

    with session_factory() as session:
        model = session.get(MLModel, uuid.UUID(model_id))
        path = settings.MODEL_DIR / model.artifact_filename
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            joblib.dump(payload, path)
        model.artifact_sha256 = file_sha256(path)  # simulate a "valid" but incompatible file
        session.commit()


@pytest.mark.parametrize(
    "payload", [{"format_version": 99, "pipeline": None}, b"not a pickle at all"]
)
def test_unloadable_artifacts_return_409(
    api_client, trained_model, settings, session_factory, payload
) -> None:
    model_id = trained_model["model"]["id"]
    _rewrite_artifact(settings, session_factory, model_id, payload)
    response = api_client.post(f"{API}/models/{model_id}/predict", json={"records": [GOOD_RECORD]})
    assert response.status_code == 409
    assert code(response) == "model_incompatible"
