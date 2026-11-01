"""Ollama provider: service, container selection, settings and API wiring.

All Ollama HTTP traffic goes through httpx.MockTransport. No local server, model or
network is needed, and no paid API is involved.
"""

import json
import logging
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai.container import AIServices
from app.ai.llm import ChatLimits, ChatMessage, OllamaChatService
from app.ai.tokens import EstimatedEncoding, TokenCounter
from app.api.deps import get_chat_service
from app.core.exceptions import (
    DataValidationError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.main import create_app
from tests.ai_fakes import FakeEncoding

MODEL = "llama3.2:3b"
SECRET_PROMPT = "confidential prompt for ollama"
USER = [ChatMessage("user", "Say hello")]


def ollama_body(**overrides) -> dict:
    body = {
        "model": MODEL,
        "created_at": "2026-10-28T10:00:00Z",
        "message": {"role": "assistant", "content": "Hello there!"},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1_200_000_000,
        "prompt_eval_count": 26,
        "eval_count": 7,
    }
    return body | overrides


class Recorder:
    def __init__(self, respond) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


def make_service(respond, **limits) -> tuple[OllamaChatService, Recorder]:
    recorder = Recorder(respond)
    client = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(recorder))
    service = OllamaChatService(
        base_url="http://ollama.test",
        default_model=MODEL,
        allowed_models=[MODEL, "qwen2.5:7b"],
        limits=ChatLimits(
            **(
                {
                    "max_messages": 5,
                    "max_input_chars": 500,
                    "max_input_tokens": 50,
                    "max_output_tokens": 256,
                    "default_output_tokens": 128,
                }
                | limits
            )
        ),
        token_counter=TokenCounter(MODEL, loader=lambda m: EstimatedEncoding(FakeEncoding())),
        client=client,
    )
    return service, recorder


def respond_json(body, status: int = 200):
    return lambda request: httpx.Response(status, json=body)


# --- successful responses -------------------------------------------------------------


def test_success_parsed_and_request_shape() -> None:
    service, recorder = make_service(respond_json(ollama_body()))
    result = service.complete([ChatMessage("system", "Be brief."), *USER])

    assert result.content == "Hello there!"
    assert result.finish_reason == "stop"
    assert result.model == MODEL
    assert result.id.startswith("ollama-")
    assert (result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens) == (
        26,
        7,
        33,
    )

    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/chat"
    assert "authorization" not in request.headers  # no API key involved
    assert recorder.body() == {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Say hello"},
        ],
        "stream": False,
        "options": {"num_predict": 128},  # default output budget, no temperature unless set
    }


def test_optional_parameters_forwarded() -> None:
    service, recorder = make_service(respond_json(ollama_body(model="qwen2.5:7b")))
    result = service.complete(USER, model="qwen2.5:7b", max_output_tokens=64, temperature=0.2)
    body = recorder.body()
    assert body["model"] == "qwen2.5:7b"
    assert body["options"] == {"num_predict": 64, "temperature": 0.2}
    assert result.model == "qwen2.5:7b"


def test_length_limit_maps_to_max_output_tokens() -> None:
    service, _ = make_service(respond_json(ollama_body(done_reason="length")))
    assert service.complete(USER).finish_reason == "max_output_tokens"


def test_cached_prompt_without_prompt_eval_count() -> None:
    body = ollama_body()
    del body["prompt_eval_count"]  # Ollama omits it when the prompt came from its cache
    service, _ = make_service(respond_json(body))
    usage = service.complete(USER).usage
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (0, 7, 7)


def test_missing_counts_and_reason_are_tolerated() -> None:
    body = {"model": MODEL, "message": {"role": "assistant", "content": "ok"}, "done": True}
    service, _ = make_service(respond_json(body))
    result = service.complete(USER)
    assert result.usage is None
    assert result.finish_reason == "stop"


def test_empty_content_is_returned_not_faked() -> None:
    service, _ = make_service(
        respond_json(ollama_body(message={"role": "assistant", "content": ""}))
    )
    assert service.complete(USER).content == ""


@pytest.mark.parametrize("bad_count", [-1, "12", 3.5, True, None])
def test_invalid_token_counts_are_ignored(bad_count) -> None:
    service, _ = make_service(respond_json(ollama_body(prompt_eval_count=bad_count)))
    assert service.complete(USER).usage.input_tokens == 0


# --- malformed / unexpected responses ---------------------------------------------------


@pytest.mark.parametrize(
    "respond",
    [
        lambda r: httpx.Response(200, content=b""),
        lambda r: httpx.Response(200, content=b"<html>proxy error</html>"),
        respond_json([1, 2, 3]),
        respond_json({"model": MODEL, "done": True}),
        respond_json(ollama_body(message={"role": "assistant"})),
        respond_json(ollama_body(message={"role": "assistant", "content": 42})),
        respond_json(ollama_body(done=False)),
        respond_json({"error": "something odd"}),
    ],
    ids=[
        "empty-body",
        "not-json",
        "json-list",
        "no-message",
        "no-content",
        "non-string-content",
        "done-false",
        "error-field",
    ],
)
def test_malformed_responses_raise_invalid_response(respond) -> None:
    service, _ = make_service(respond)
    with pytest.raises(ProviderError) as exc_info:
        service.complete(USER)
    assert exc_info.value.code == "provider_invalid_response"
    assert exc_info.value.status_code == 502


# --- transport and HTTP errors -----------------------------------------------------------


def test_connection_refused_maps_to_unavailable() -> None:
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    service, _ = make_service(refuse)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        service.complete(USER)
    assert exc_info.value.status_code == 502
    assert "OLLAMA_BASE_URL" in exc_info.value.message


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_timeouts_map_to_provider_timeout(error) -> None:
    def slow(request):
        raise error("timed out", request=request)

    service, _ = make_service(slow)
    with pytest.raises(ProviderTimeoutError) as exc_info:
        service.complete(USER)
    assert exc_info.value.status_code == 504
    assert "OLLAMA_TIMEOUT_SECONDS" in exc_info.value.message


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, {"error": 'model "llama3.2:3b" not found, try pulling it first'}),
        (500, {"error": 'model "llama3.2:3b" not found'}),
    ],
)
def test_unavailable_model_gives_clear_safe_error(status, body) -> None:
    service, _ = make_service(respond_json(body, status))
    with pytest.raises(ProviderError) as exc_info:
        service.complete(USER)
    error = exc_info.value
    assert error.code == "provider_model_not_found"
    assert error.status_code == 502
    assert f"ollama pull {MODEL}" in error.message
    assert "try pulling it first" not in error.message  # provider text is not echoed


@pytest.mark.parametrize(
    ("status", "error_type", "http_status"),
    [
        (400, ProviderRequestRejectedError, 422),
        (500, ProviderUnavailableError, 502),
        (503, ProviderUnavailableError, 502),
    ],
)
def test_http_errors_are_mapped(status, error_type, http_status) -> None:
    service, _ = make_service(respond_json({"error": "internal detail /home/x"}, status))
    with pytest.raises(error_type) as exc_info:
        service.complete(USER)
    assert exc_info.value.status_code == http_status
    assert "internal detail" not in exc_info.value.message


def test_non_json_error_body_is_handled() -> None:
    service, _ = make_service(lambda r: httpx.Response(502, content=b"Bad Gateway"))
    with pytest.raises(ProviderUnavailableError):
        service.complete(USER)


# --- validation happens before any call ---------------------------------------------------


def _never_called(request):
    raise AssertionError("Ollama must not be called for invalid input")


@pytest.mark.parametrize(
    ("messages", "kwargs", "message"),
    [
        (USER, {"model": "gpt-5.4-mini"}, "not allowed"),
        ([ChatMessage("user", "word " * 60)], {}, "tokens"),
        ([ChatMessage("user", "x" * 501)], {}, "characters"),
        (USER, {"max_output_tokens": 1000}, "may not exceed 256"),
        ([ChatMessage("system", "only system")], {}, "user message"),
    ],
)
def test_invalid_requests_never_reach_ollama(messages, kwargs, message) -> None:
    service, recorder = make_service(_never_called)
    with pytest.raises(DataValidationError, match=message):
        service.complete(messages, **kwargs)
    assert recorder.requests == []


def test_logs_never_contain_prompt_or_reply(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    service, _ = make_service(respond_json(ollama_body()))
    service.complete([ChatMessage("user", SECRET_PROMPT)])
    failing, _ = make_service(respond_json({"error": "boom"}, 500))
    with pytest.raises(ProviderUnavailableError):
        failing.complete([ChatMessage("user", SECRET_PROMPT)])
    assert SECRET_PROMPT not in caplog.text
    assert "Hello there!" not in caplog.text
    assert "provider=ollama" in caplog.text


def test_close_releases_http_client() -> None:
    service, _ = make_service(respond_json(ollama_body()))
    service.close()
    with pytest.raises(ProviderUnavailableError):  # closed client -> transport error
        service.complete(USER)


# --- settings ------------------------------------------------------------------------------


def test_default_provider_is_still_openai(make_settings) -> None:
    settings = make_settings()
    assert settings.LLM_PROVIDER == "openai"
    assert settings.active_llm_model == settings.OPENAI_MODEL


def test_allowed_models_follow_provider(make_settings) -> None:
    ollama = make_settings(LLM_PROVIDER="ollama", OLLAMA_ALLOWED_MODELS="qwen2.5:7b, mistral")
    assert ollama.active_llm_model == MODEL
    assert ollama.allowed_llm_models == [MODEL, "qwen2.5:7b", "mistral"]
    openai = make_settings(LLM_PROVIDER="openai", OPENAI_ALLOWED_MODELS="gpt-x")
    assert openai.allowed_llm_models == ["gpt-5.4-mini", "gpt-x"]
    assert MODEL not in openai.allowed_llm_models


def test_ollama_url_validation(make_settings) -> None:
    assert make_settings(OLLAMA_BASE_URL="http://127.0.0.1:11434/").OLLAMA_BASE_URL == (
        "http://127.0.0.1:11434"
    )
    with pytest.raises(ValidationError, match="OLLAMA_BASE_URL"):
        make_settings(OLLAMA_BASE_URL="127.0.0.1:11434")
    with pytest.raises(ValidationError):
        make_settings(LLM_PROVIDER="anthropic")


# --- container selection --------------------------------------------------------------------


def test_container_selects_ollama_without_api_key(make_settings) -> None:
    ai = AIServices(make_settings(LLM_PROVIDER="ollama"))
    service = ai.chat_service()
    assert isinstance(service, OllamaChatService)
    assert service.default_model == MODEL
    assert service.allowed_models == [MODEL]
    assert ai.chat_service() is service  # built once
    assert ai.token_counter.default_model == MODEL
    status = ai.status()["llm"]
    assert status == {
        "provider": "ollama",
        "configured": True,
        "requires_api_key": False,
        "default_model": MODEL,
        "allowed_models": [MODEL],
    }
    ai.shutdown()
    assert service._client.is_closed  # HTTP connection pool released on shutdown
    assert ai.chat_service() is not service  # recreated after shutdown


def test_container_openai_without_key_unchanged(make_settings) -> None:
    ai = AIServices(make_settings(LLM_PROVIDER="openai"))
    with pytest.raises(ProviderNotConfiguredError) as exc_info:
        ai.chat_service()
    assert "OPENAI_API_KEY" in exc_info.value.message
    assert "LLM_PROVIDER=ollama" in exc_info.value.message
    status = ai.status()["llm"]
    assert (status["provider"], status["configured"], status["requires_api_key"]) == (
        "openai",
        False,
        True,
    )
    assert ai.token_counter.default_model == "gpt-5.4-mini"


def test_container_openai_with_key_unchanged(make_settings) -> None:
    pytest.importorskip("openai")
    from app.ai.llm import OpenAIChatService

    ai = AIServices(make_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-test-not-real"))
    service = ai.chat_service()
    assert isinstance(service, OpenAIChatService)
    assert service.allowed_models == ["gpt-5.4-mini"]
    assert ai.status()["llm"]["configured"] is True
    ai.shutdown()


def test_ollama_provider_needs_no_openai_package(make_settings, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)
    ai = AIServices(make_settings(LLM_PROVIDER="ollama"))
    assert isinstance(ai.chat_service(), OllamaChatService)
    ai.shutdown()


# --- API wiring ---------------------------------------------------------------------------------


@pytest.fixture
def ollama_app(make_settings):
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    app = create_app(make_settings(LLM_PROVIDER="ollama"))
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="ollama@example.com", role="admin", is_active=True
    )
    app.state.ai.token_counter = TokenCounter(
        MODEL, loader=lambda m: EstimatedEncoding(FakeEncoding())
    )
    return app


def _override_chat(app, respond) -> Recorder:
    service, recorder = make_service(respond, max_input_tokens=8000, max_input_chars=32000)
    app.dependency_overrides[get_chat_service] = lambda: service
    return recorder


def test_chat_endpoint_with_ollama(ollama_app) -> None:
    recorder = _override_chat(ollama_app, respond_json(ollama_body()))
    with TestClient(ollama_app) as client:
        response = client.post(
            "/api/v1/llm/chat",
            json={
                "messages": [{"role": "user", "content": "Say hello"}],
                "model": MODEL,
                "max_output_tokens": 64,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"id", "model", "content", "finish_reason", "usage"}  # unchanged contract
    assert body["content"] == "Hello there!"
    assert body["usage"] == {"input_tokens": 26, "output_tokens": 7, "total_tokens": 33}
    assert recorder.body()["options"]["num_predict"] == 64


def test_chat_endpoint_rejects_model_of_other_provider(ollama_app) -> None:
    _override_chat(ollama_app, _never_called)
    with TestClient(ollama_app) as client:
        response = client.post(
            "/api/v1/llm/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "model": "gpt-5.4-mini"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "data_validation_error"


def test_chat_endpoint_when_ollama_is_down(ollama_app) -> None:
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    _override_chat(ollama_app, refuse)
    with TestClient(ollama_app) as client:
        response = client.post(
            "/api/v1/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]}
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "Traceback" not in response.text


def test_real_container_wiring_hits_configured_ollama_url(make_settings) -> None:
    """No dependency override: the app's own container builds the Ollama client."""
    import uuid
    from app.api.deps import get_current_user
    from app.database.models.user import User

    app = create_app(make_settings(LLM_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:9"))
    app.dependency_overrides[get_current_user] = lambda: User(
        id=uuid.uuid4(), email="ollama@example.com", role="admin", is_active=True
    )
    with TestClient(app) as client:
        status = client.get("/api/v1/ai/status").json()["llm"]
        response = client.post(
            "/api/v1/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]}
        )
    assert status["provider"] == "ollama" and status["configured"] is True
    # Port 9 has no Ollama server: the real client fails safely with a 502, not a 500/503.
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unavailable"


def test_token_count_defaults_to_ollama_model_and_is_flagged_approximate(ollama_app) -> None:
    with TestClient(ollama_app) as client:
        response = client.post("/api/v1/tokens/count", json={"text": "one two three"})
    assert response.json() == {
        "model": MODEL,
        "encoding": "fake_bpe",
        "tokens": 3,
        "approximate": True,
    }
