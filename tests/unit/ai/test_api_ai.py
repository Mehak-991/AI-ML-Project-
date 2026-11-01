"""AI endpoint tests: schemas, bounds, error mapping. All services are fakes."""

import sys

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings import EmbeddingService
from app.ai.model_cache import ModelCache
from app.ai.runtime import InferenceExecutor
from app.ai.tokens import TokenCounter
from app.api.deps import get_chat_service, get_embedding_service, get_text_classifier
from app.core.exceptions import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.main import create_app
from app.schemas.ai import (
    AIStatusResponse,
    ChatResponse,
    ClassificationResponse,
    EmbeddingResponse,
    TokenCountResponse,
)
from app.schemas.common import ErrorResponse
from tests.ai_fakes import FakeChat, FakeEmbeddingBackend, FakeEncoding, fake_classifier

API = "/api/v1"


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
def ai_client(app, chat):
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    mock_admin = User(
        id=uuid.uuid4(),
        email="ai_admin@example.com",
        full_name="AI Admin",
        hashed_password="mock",
        role="admin",
        is_active=True,
    )
    executor = InferenceExecutor(max_workers=1, timeout_seconds=5)
    embedder = EmbeddingService(
        model_name="fake-embedder",
        backend_factory=lambda: FakeEmbeddingBackend(dimension=4),
        cache=ModelCache(),
        executor=executor,
        batch_size=2,
        max_texts=5,
        max_chars=100,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_embedding_service] = lambda: embedder
    app.dependency_overrides[get_text_classifier] = lambda: fake_classifier()
    app.dependency_overrides[get_chat_service] = lambda: chat
    app.state.ai.token_counter = TokenCounter("gpt-test", loader=lambda m: FakeEncoding())
    with TestClient(app) as client:
        yield client
    executor.shutdown()


def error_code(response) -> str:
    return ErrorResponse.model_validate(response.json()).error.code


# --- embeddings ----------------------------------------------------------------------


def test_embeddings_endpoint(ai_client) -> None:
    response = ai_client.post(f"{API}/embeddings", json={"texts": ["a", "b", "c"]})
    assert response.status_code == 200
    body = EmbeddingResponse.model_validate(response.json())
    assert (body.model, body.dimension, body.count) == ("fake-embedder", 4, 3)
    assert [item.index for item in body.data] == [0, 1, 2]
    assert all(len(item.embedding) == 4 for item in body.data)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"texts": []}, "validation_error"),  # schema bound
        ({"texts": [""]}, "validation_error"),  # schema min_length
        ({"texts": ["x"], "extra": 1}, "validation_error"),  # unknown field
        ({"texts": ["x"] * 6}, "data_validation_error"),  # service limit (max_texts=5)
        ({"texts": ["x" * 101]}, "data_validation_error"),  # service limit (max_chars=100)
        ({"texts": ["   "]}, "data_validation_error"),  # blank after strip
    ],
)
def test_embeddings_validation(ai_client, payload, code) -> None:
    response = ai_client.post(f"{API}/embeddings", json=payload)
    assert response.status_code == 422
    assert error_code(response) == code


# --- classification ------------------------------------------------------------------


def test_classify_endpoint(ai_client) -> None:
    response = ai_client.post(
        f"{API}/nlp/classify", json={"texts": ["good stuff", "awful"], "top_k": 2}
    )
    assert response.status_code == 200
    body = ClassificationResponse.model_validate(response.json())
    assert body.results[0].labels[0].label == "POSITIVE"
    assert body.results[1].labels[0].label == "NEGATIVE"
    assert len(body.results[0].labels) == 2


def test_classify_top_k_bounds(ai_client) -> None:
    assert (
        ai_client.post(f"{API}/nlp/classify", json={"texts": ["x"], "top_k": 9}).status_code == 422
    )


# --- chat ----------------------------------------------------------------------------


def test_chat_endpoint(ai_client, chat) -> None:
    response = ai_client.post(
        f"{API}/llm/chat",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "max_output_tokens": 64,
            "temperature": 0.3,
        },
    )
    assert response.status_code == 200
    body = ChatResponse.model_validate(response.json())
    assert body.content == "fake reply #1"
    assert body.usage.total_tokens == 13
    assert chat.calls[0]["max_output_tokens"] == 64
    assert chat.calls[0]["temperature"] == 0.3


@pytest.mark.parametrize(
    "payload",
    [
        {"messages": []},
        {"messages": [{"role": "tool", "content": "x"}]},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": [{"role": "user", "content": "x"}], "temperature": 3},
        {"messages": [{"role": "user", "content": "x"}], "max_output_tokens": 1},
    ],
)
def test_chat_schema_validation(ai_client, payload) -> None:
    response = ai_client.post(f"{API}/llm/chat", json=payload)
    assert response.status_code == 422
    assert error_code(response) == "validation_error"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (ProviderRateLimitError(headers={"Retry-After": "7"}), 429, "provider_rate_limited"),
        (ProviderTimeoutError(), 504, "provider_timeout"),
        (ProviderAuthenticationError(), 502, "provider_authentication_failed"),
    ],
)
def test_chat_provider_errors(ai_client, chat, error, status, code) -> None:
    chat.error = error
    response = ai_client.post(
        f"{API}/llm/chat", json={"messages": [{"role": "user", "content": "x"}]}
    )
    assert response.status_code == status
    assert error_code(response) == code
    if status == 429:
        assert response.headers["retry-after"] == "7"


def test_chat_without_api_key_is_actionable(ai_client: TestClient) -> None:
    response = ai_client.post(f"{API}/llm/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert response.status_code == 503
    error = ErrorResponse.model_validate(response.json()).error
    assert error.code == "provider_not_configured"
    assert "OPENAI_API_KEY" in error.message


def test_analyze_without_api_key(ai_client: TestClient) -> None:
    response = ai_client.post(f"{API}/nlp/analyze", json={"text": "hello"})
    assert response.status_code == 503
    assert error_code(response) == "provider_not_configured"


# --- tokens --------------------------------------------------------------------------


def test_token_count_text(ai_client) -> None:
    response = ai_client.post(f"{API}/tokens/count", json={"text": "one two three"})
    body = TokenCountResponse.model_validate(response.json())
    assert (body.tokens, body.encoding, body.approximate, body.model) == (
        3,
        "fake_bpe",
        False,
        "gpt-test",
    )


def test_token_count_messages(ai_client) -> None:
    response = ai_client.post(
        f"{API}/tokens/count",
        json={"messages": [{"role": "user", "content": "hello there"}], "model": "other"},
    )
    assert response.status_code == 200
    assert response.json()["tokens"] == 3 + 3 + 1 + 2
    assert response.json()["model"] == "other"


@pytest.mark.parametrize(
    "payload", [{}, {"text": "a", "messages": [{"role": "user", "content": "b"}]}]
)
def test_token_count_requires_exactly_one_input(ai_client, payload) -> None:
    assert ai_client.post(f"{API}/tokens/count", json=payload).status_code == 422


# --- real container wiring (no fakes) -------------------------------------------------


def test_status_reports_configuration_without_secrets(make_settings) -> None:
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    app = create_app(make_settings(OPENAI_API_KEY="sk-must-not-leak", OPENAI_ALLOWED_MODELS="a,b"))
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="u@example.com", role="admin", is_active=True
    )
    with TestClient(app) as client:
        response = client.get(f"{API}/ai/status")
    assert response.status_code == 200
    body = AIStatusResponse.model_validate(response.json())
    assert body.llm["configured"] is True
    assert body.llm["allowed_models"] == ["gpt-5.4-mini", "a", "b"]
    assert body.loaded_models == []
    assert "sk-must-not-leak" not in response.text
    assert set(body.packages) >= {"torch", "transformers", "sentence_transformers", "openai"}


def test_embeddings_without_sentence_transformers(monkeypatch, make_settings) -> None:
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    app = create_app(make_settings(AI_DEVICE="cpu"))
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="u@example.com", role="admin", is_active=True
    )
    with TestClient(app) as client:
        response = client.post(f"{API}/embeddings", json={"texts": ["hello"]})
    assert response.status_code == 503
    error = ErrorResponse.model_validate(response.json()).error
    assert error.code == "optional_dependency_missing"
    assert ".[nlp]" in error.details["install"]


def test_classify_without_torch(monkeypatch, make_settings) -> None:
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    monkeypatch.setitem(sys.modules, "torch", None)
    app = create_app(make_settings())
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="u@example.com", role="admin", is_active=True
    )
    with TestClient(app) as client:
        response = client.post(f"{API}/nlp/classify", json={"texts": ["hello"]})
    assert response.status_code == 503
    assert error_code(response) == "optional_dependency_missing"


def test_openapi_documents_ai_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/embeddings", "/nlp/classify", "/llm/chat", "/tokens/count", "/nlp/analyze"):
        assert "post" in paths[f"{API}{path}"]
    assert "get" in paths[f"{API}/ai/status"]


def test_token_count_respects_configured_char_limit(make_settings) -> None:
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    app = create_app(make_settings(TOKENIZER_MAX_TEXT_CHARS=10))
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="u@example.com", role="admin", is_active=True
    )
    app.state.ai.token_counter = TokenCounter("m", loader=lambda m: None)
    with TestClient(app) as client:
        assert client.post(f"{API}/tokens/count", json={"text": "x" * 10}).status_code == 200
        response = client.post(f"{API}/tokens/count", json={"text": "x" * 11})
    assert response.status_code == 422
    assert error_code(response) == "data_validation_error"


def test_ai_endpoints_require_authentication(app) -> None:
    """Finding 1.1 verification: all AI endpoints return 401 without bearer token."""
    with TestClient(app) as client:
        assert client.get(f"{API}/ai/status").status_code == 401
        assert client.post(f"{API}/embeddings", json={"texts": ["a"]}).status_code == 401
        assert client.post(f"{API}/nlp/classify", json={"texts": ["a"]}).status_code == 401
        assert (
            client.post(
                f"{API}/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]}
            ).status_code
            == 401
        )
        assert client.post(f"{API}/tokens/count", json={"text": "a"}).status_code == 401
        assert client.post(f"{API}/nlp/analyze", json={"text": "a"}).status_code == 401


def test_ai_role_enforcement_for_chat_and_analyze(app) -> None:
    """Finding 1.1 verification: viewer role gets 403 on chat and analyze; admin is allowed."""
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    viewer_user = User(
        id=uuid.uuid4(),
        email="viewer@example.com",
        full_name="Viewer User",
        hashed_password="mock",
        role="viewer",
        is_active=True,
    )
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    with TestClient(app) as client:
        assert (
            client.post(
                f"{API}/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]}
            ).status_code
            == 403
        )
        assert client.post(f"{API}/nlp/analyze", json={"text": "hi"}).status_code == 403
