"""OpenAI chat service tests.

The real `openai` SDK is used with an in-memory httpx transport, so actual SDK
exception classes are raised and mapped — but no request leaves the process
and no paid API call is made.
"""

import json
import logging

import httpx
import pytest

openai = pytest.importorskip("openai")

from app.ai.llm import ChatLimits, ChatMessage, OpenAIChatService  # noqa: E402
from app.ai.tokens import TokenCounter  # noqa: E402
from app.core.exceptions import (  # noqa: E402
    DataValidationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tests.ai_fakes import FakeEncoding  # noqa: E402

SECRET_KEY = "sk-test-super-secret-key"
SECRET_PROMPT = "my confidential prompt text"


def responses_payload(**overrides) -> dict:
    payload = {
        "id": "resp_123",
        "object": "response",
        "created_at": 1_700_000_000,
        "status": "completed",
        "model": "gpt-test-2026-01-01",
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello there!", "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 12,
            "output_tokens": 3,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        "error": None,
        "incomplete_details": None,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }
    return payload | overrides


def error_response(status: int, code: str | None = None, headers: dict | None = None):
    body = {"error": {"message": "provider says no", "type": "error", "code": code, "param": None}}
    return httpx.Response(status, json=body, headers=headers or {})


class Recorder:
    def __init__(self, respond) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


def make_service(respond, **limit_overrides) -> tuple[OpenAIChatService, Recorder]:
    recorder = Recorder(respond)
    client = openai.OpenAI(
        api_key=SECRET_KEY,
        base_url="https://llm.invalid/v1",
        max_retries=0,
        timeout=5,
        http_client=httpx.Client(transport=httpx.MockTransport(recorder)),
    )
    service = OpenAIChatService(
        api_key=SECRET_KEY,
        default_model="gpt-test",
        allowed_models=["gpt-test", "gpt-other"],
        limits=ChatLimits(
            **(
                {
                    "max_messages": 5,
                    "max_input_chars": 500,
                    "max_input_tokens": 50,
                    "max_output_tokens": 256,
                    "default_output_tokens": 128,
                }
                | limit_overrides
            )
        ),
        token_counter=TokenCounter("gpt-test", loader=lambda m: FakeEncoding()),
        client=client,
    )
    return service, recorder


USER = [ChatMessage("user", "Say hello")]


def test_successful_completion_and_request_shape() -> None:
    service, recorder = make_service(lambda r: httpx.Response(200, json=responses_payload()))
    result = service.complete([ChatMessage("system", "Be brief."), *USER])

    assert result.content == "Hello there!"
    assert result.finish_reason == "stop"
    assert result.model == "gpt-test-2026-01-01"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 3)

    request = recorder.requests[0]
    assert request.url.path.endswith("/responses")
    assert request.headers["authorization"] == f"Bearer {SECRET_KEY}"
    body = recorder.body()
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["max_output_tokens"] == 128  # default budget
    assert "temperature" not in body  # omitted unless requested
    assert body["input"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Say hello"},
    ]


def test_optional_parameters_are_forwarded() -> None:
    service, recorder = make_service(lambda r: httpx.Response(200, json=responses_payload()))
    service.complete(USER, model="gpt-other", max_output_tokens=64, temperature=0.2)
    body = recorder.body()
    assert (body["model"], body["max_output_tokens"], body["temperature"]) == ("gpt-other", 64, 0.2)


def test_incomplete_response_reports_reason() -> None:
    payload = responses_payload(
        status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    service, _ = make_service(lambda r: httpx.Response(200, json=payload))
    assert service.complete(USER).finish_reason == "max_output_tokens"


@pytest.mark.parametrize(
    ("respond", "error_type", "status"),
    [
        (lambda r: error_response(401, "invalid_api_key"), ProviderAuthenticationError, 502),
        (lambda r: error_response(403), ProviderAuthenticationError, 502),
        (lambda r: error_response(429, "rate_limit_exceeded"), ProviderRateLimitError, 429),
        (lambda r: error_response(429, "insufficient_quota"), ProviderQuotaExceededError, 429),
        (
            lambda r: error_response(400, "context_length_exceeded"),
            ProviderRequestRejectedError,
            422,
        ),
        (lambda r: error_response(422), ProviderRequestRejectedError, 422),
        (lambda r: error_response(500), ProviderUnavailableError, 502),
        (lambda r: error_response(503), ProviderUnavailableError, 502),
    ],
)
def test_status_errors_are_mapped(respond, error_type, status) -> None:
    service, _ = make_service(respond)
    with pytest.raises(error_type) as exc_info:
        service.complete(USER)
    assert exc_info.value.status_code == status
    assert "provider says no" not in exc_info.value.message  # provider text not echoed


def test_model_not_found_is_explained() -> None:
    service, _ = make_service(lambda r: error_response(404, "model_not_found"))
    with pytest.raises(ProviderError) as exc_info:
        service.complete(USER)
    assert exc_info.value.code == "provider_model_not_found"
    assert "OPENAI_MODEL" in exc_info.value.message


def test_rejected_request_exposes_provider_code() -> None:
    service, _ = make_service(lambda r: error_response(400, "context_length_exceeded"))
    with pytest.raises(ProviderRequestRejectedError) as exc_info:
        service.complete(USER)
    assert exc_info.value.details["provider_code"] == "context_length_exceeded"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [({"retry-after": "7"}, "7"), ({"retry-after-ms": "1500"}, "2"), ({}, None)],
)
def test_rate_limit_retry_after(headers, expected) -> None:
    service, _ = make_service(lambda r: error_response(429, "rate_limit_exceeded", headers))
    with pytest.raises(ProviderRateLimitError) as exc_info:
        service.complete(USER)
    retry_after = (exc_info.value.headers or {}).get("Retry-After")
    assert retry_after == expected


def test_timeout_is_mapped() -> None:
    def timeout(request):
        raise httpx.ReadTimeout("timed out", request=request)

    service, _ = make_service(timeout)
    with pytest.raises(ProviderTimeoutError) as exc_info:
        service.complete(USER)
    assert exc_info.value.status_code == 504


def test_network_failure_is_mapped() -> None:
    def unreachable(request):
        raise httpx.ConnectError("connection refused", request=request)

    service, _ = make_service(unreachable)
    with pytest.raises(ProviderUnavailableError):
        service.complete(USER)


def test_sdk_retries_are_configured_on_real_client() -> None:
    service = OpenAIChatService(
        api_key=SECRET_KEY,
        default_model="m",
        allowed_models=["m"],
        limits=ChatLimits(),
        token_counter=TokenCounter("m", loader=lambda m: None),
        timeout_seconds=12.5,
        max_retries=4,
    )
    assert service._client.max_retries == 4
    assert service._client.timeout == 12.5


# --- input validation (no provider call happens) --------------------------------------


def _never_called(request):
    raise AssertionError("provider must not be called for invalid input")


@pytest.mark.parametrize(
    ("messages", "kwargs", "message"),
    [
        ([], {}, "At least one message"),
        ([ChatMessage("user", "hi")] * 6, {}, "At most 5"),
        ([ChatMessage("user", "  ")], {}, "Invalid chat messages"),
        ([ChatMessage("tool", "hi")], {}, "Invalid chat messages"),  # type: ignore[arg-type]
        ([ChatMessage("system", "only system")], {}, "user message"),
        ([ChatMessage("user", "x" * 501)], {}, "characters"),
        ([ChatMessage("user", "word " * 60)], {}, "tokens"),
        (USER, {"model": "gpt-expensive"}, "not allowed"),
        (USER, {"max_output_tokens": 1000}, "may not exceed 256"),
    ],
)
def test_invalid_requests_never_reach_provider(messages, kwargs, message) -> None:
    service, recorder = make_service(_never_called)
    with pytest.raises(DataValidationError, match=message):
        service.complete(messages, **kwargs)
    assert recorder.requests == []


# --- privacy ------------------------------------------------------------------------


def test_logs_never_contain_key_or_content(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    service, _ = make_service(lambda r: httpx.Response(200, json=responses_payload()))
    service.complete([ChatMessage("user", SECRET_PROMPT)])
    service_err, _ = make_service(lambda r: error_response(401))
    with pytest.raises(ProviderAuthenticationError):
        service_err.complete([ChatMessage("user", SECRET_PROMPT)])
    assert SECRET_KEY not in caplog.text
    assert SECRET_PROMPT not in caplog.text
    assert "Hello there!" not in caplog.text
    assert "LLM call model=" in caplog.text  # metadata is still logged
