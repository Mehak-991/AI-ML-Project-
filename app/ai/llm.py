"""LLM chat completion behind a provider-neutral interface (`ChatService`), implemented for
the OpenAI Responses API and for a local Ollama server (`/api/chat`).

Privacy defaults: prompts and completions are never logged unless
LLM_LOG_CONTENT=true, the API key is never logged, and OpenAI requests are sent with
`store=False` so the provider does not retain them for later retrieval.
"""

import logging
import math
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from app.ai.optional import require
from app.ai.tokens import TokenCounter
from app.core.exceptions import (
    AppError,
    DataValidationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderRequestRejectedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

Role = Literal["system", "user", "assistant"]
ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class ChatUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ChatResult:
    id: str
    model: str
    content: str
    finish_reason: str
    usage: ChatUsage | None


@dataclass(frozen=True)
class ChatLimits:
    max_messages: int = 50
    max_input_chars: int = 32_000
    max_input_tokens: int = 8_000
    max_output_tokens: int = 4_096
    default_output_tokens: int = 1_024


class ChatService(Protocol):
    default_model: str

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult: ...


def validate_chat_request(
    messages: list[ChatMessage],
    *,
    model: str,
    allowed_models: list[str],
    max_output_tokens: int | None,
    limits: ChatLimits,
    token_counter: TokenCounter,
) -> int:
    """Validate a chat request; return the output-token budget to use."""
    if model not in allowed_models:
        raise DataValidationError(
            f"Model '{model}' is not allowed.", details={"allowed_models": allowed_models}
        )
    if not messages:
        raise DataValidationError("At least one message is required.")
    if len(messages) > limits.max_messages:
        raise DataValidationError(f"At most {limits.max_messages} messages per request.")
    errors = []
    for index, message in enumerate(messages):
        if message.role not in ROLES:
            errors.append({"index": index, "message": f"Unsupported role '{message.role}'."})
        if not message.content or not message.content.strip():
            errors.append({"index": index, "message": "Message content must not be empty."})
    if errors:
        raise DataValidationError("Invalid chat messages.", details=errors)
    if not any(m.role == "user" for m in messages):
        raise DataValidationError("At least one user message is required.")

    total_chars = sum(len(m.content) for m in messages)
    if total_chars > limits.max_input_chars:
        raise DataValidationError(
            f"Input is {total_chars} characters; the limit is {limits.max_input_chars}."
        )
    counted = token_counter.count_messages([(m.role, m.content) for m in messages], model)
    if counted.tokens > limits.max_input_tokens:
        raise DataValidationError(
            f"Input is about {counted.tokens} tokens; the limit is {limits.max_input_tokens}.",
            details={"input_tokens": counted.tokens, "approximate": counted.approximate},
        )

    budget = max_output_tokens or limits.default_output_tokens
    if budget > limits.max_output_tokens:
        raise DataValidationError(f"max_output_tokens may not exceed {limits.max_output_tokens}.")
    return budget


def _retry_after_header(exc: Any) -> dict[str, str] | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    raw = response.headers.get("retry-after")
    if raw is None and (ms := response.headers.get("retry-after-ms")):
        try:
            raw = str(float(ms) / 1000)
        except ValueError:
            raw = None
    try:
        seconds = math.ceil(float(raw)) if raw is not None else None
    except ValueError:
        seconds = None
    return {"Retry-After": str(max(seconds, 1))} if seconds is not None else None


def map_openai_error(exc: Exception, *, model: str) -> AppError:
    """Translate OpenAI SDK exceptions into client-safe application errors."""
    import openai

    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    logger.warning(
        "OpenAI request failed: %s status=%s code=%s request_id=%s",
        type(exc).__name__,
        status,
        code,
        getattr(exc, "request_id", None),
    )
    # APITimeoutError subclasses APIConnectionError, so it must be checked first.
    if isinstance(exc, openai.APITimeoutError):
        return ProviderTimeoutError()
    if isinstance(exc, openai.APIConnectionError):
        return ProviderUnavailableError()
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthenticationError()
    if isinstance(exc, openai.RateLimitError):
        if code == "insufficient_quota":
            return ProviderQuotaExceededError()
        return ProviderRateLimitError(headers=_retry_after_header(exc))
    if isinstance(exc, openai.NotFoundError):
        return ProviderError(
            f"The provider does not recognise model '{model}'. Check OPENAI_MODEL.",
            code="provider_model_not_found",
        )
    if isinstance(
        exc, openai.BadRequestError | openai.UnprocessableEntityError | openai.ConflictError
    ):
        return ProviderRequestRejectedError(
            details={"provider_code": code, "param": getattr(exc, "param", None)}
        )
    if isinstance(exc, openai.APIStatusError) and (status or 0) >= 500:
        return ProviderUnavailableError()
    return ProviderError()


class OpenAIChatService:
    """Chat completion using the official `openai` SDK (Responses API)."""

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        allowed_models: list[str],
        limits: ChatLimits,
        token_counter: TokenCounter,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        base_url: str | None = None,
        organization: str | None = None,
        log_content: bool = False,
        client: Any = None,
    ) -> None:
        self.default_model = default_model
        self.allowed_models = allowed_models
        self.limits = limits
        self._token_counter = token_counter
        self._log_content = log_content
        if not log_content:
            # The SDK logs full request bodies (prompts) at DEBUG on the "openai" logger.
            # Keep that out of the logs even when the app runs with LOG_LEVEL=DEBUG.
            sdk_logger = logging.getLogger("openai")
            if sdk_logger.getEffectiveLevel() < logging.INFO:
                sdk_logger.setLevel(logging.INFO)
        if client is None:
            openai = require("openai", "LLM chat completion")
            # The SDK retries connection errors, 408/409/429 and 5xx with exponential backoff.
            client = openai.OpenAI(
                api_key=api_key,
                base_url=base_url,
                organization=organization,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )
        self._client = client

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        import openai

        model = model or self.default_model
        budget = validate_chat_request(
            messages,
            model=model,
            allowed_models=self.allowed_models,
            max_output_tokens=max_output_tokens,
            limits=self.limits,
            token_counter=self._token_counter,
        )
        params: dict[str, Any] = {
            "model": model,
            "input": [{"role": m.role, "content": m.content} for m in messages],
            "max_output_tokens": budget,
            "store": False,
        }
        if temperature is not None:  # some reasoning models reject temperature entirely
            params["temperature"] = temperature
        if self._log_content:
            logger.debug("LLM request messages=%s", params["input"])

        started = time.perf_counter()
        try:
            response = self._client.responses.create(**params)
        except openai.OpenAIError as exc:
            raise map_openai_error(exc, model=model) from exc

        result = self._to_result(response, model)
        logger.info(
            "LLM call model=%s finish=%s input_tokens=%s output_tokens=%s duration_ms=%d",
            result.model,
            result.finish_reason,
            result.usage.input_tokens if result.usage else None,
            result.usage.output_tokens if result.usage else None,
            (time.perf_counter() - started) * 1000,
        )
        if self._log_content:
            logger.debug("LLM response content=%s", result.content)
        return result

    @staticmethod
    def _to_result(response: Any, requested_model: str) -> ChatResult:
        if getattr(response, "status", None) == "failed":
            raise ProviderError("The LLM provider reported a failed response.")
        finish_reason = "stop"
        if getattr(response, "status", None) == "incomplete":
            details = getattr(response, "incomplete_details", None)
            finish_reason = getattr(details, "reason", None) or "incomplete"
        usage = getattr(response, "usage", None)
        return ChatResult(
            id=str(getattr(response, "id", "")),
            model=str(getattr(response, "model", None) or requested_model),
            content=getattr(response, "output_text", "") or "",
            finish_reason=finish_reason,
            usage=ChatUsage(
                input_tokens=int(usage.input_tokens),
                output_tokens=int(usage.output_tokens),
                total_tokens=int(usage.total_tokens),
            )
            if usage
            else None,
        )


# Ollama "done_reason" -> this API's finish_reason vocabulary (shared with OpenAI).
_OLLAMA_FINISH_REASONS = {"stop": "stop", "length": "max_output_tokens"}


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class OllamaChatService:
    """Chat completion against a local Ollama server (`POST /api/chat`, non-streaming).

    No API key is involved. The same request validation (allow-list, message, character
    and token limits) runs before any call, and failures map to the same provider error
    codes as the OpenAI service. Prompt/response text is never logged unless log_content.
    """

    def __init__(
        self,
        *,
        base_url: str,
        default_model: str,
        allowed_models: list[str],
        limits: ChatLimits,
        token_counter: TokenCounter,
        timeout_seconds: float = 180.0,
        log_content: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.default_model = default_model
        self.allowed_models = allowed_models
        self.limits = limits
        self._token_counter = token_counter
        self._log_content = log_content
        # Short connect timeout (server down -> fail fast); long read timeout (CPU inference).
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
        )

    def close(self) -> None:
        self._client.close()

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        model = model or self.default_model
        budget = validate_chat_request(
            messages,
            model=model,
            allowed_models=self.allowed_models,
            max_output_tokens=max_output_tokens,
            limits=self.limits,
            token_counter=self._token_counter,
        )
        options: dict[str, Any] = {"num_predict": budget}
        if temperature is not None:
            options["temperature"] = temperature
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": options,
        }
        if self._log_content:
            logger.debug("Ollama request messages=%s", payload["messages"])

        started = time.perf_counter()
        try:
            response = self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("Ollama request timed out: %s", type(exc).__name__)
            raise ProviderTimeoutError(
                "The local Ollama model did not respond in time. Try a shorter prompt, a "
                "smaller max_output_tokens, or raise OLLAMA_TIMEOUT_SECONDS."
            ) from exc
        except httpx.HTTPError as exc:  # connection refused, DNS, protocol errors
            logger.warning("Ollama request failed: %s", type(exc).__name__)
            raise ProviderUnavailableError(
                "The Ollama server is not reachable. Start Ollama and check OLLAMA_BASE_URL."
            ) from exc
        except RuntimeError as exc:
            if not self._client.is_closed:
                raise
            # A request racing application shutdown, after close() released the client.
            raise ProviderUnavailableError("The LLM service is shutting down. Retry.") from exc

        if response.status_code != 200:
            raise self._map_status_error(response, model)
        result = self._to_result(response, model)
        logger.info(
            "LLM call provider=ollama model=%s finish=%s input_tokens=%s output_tokens=%s "
            "duration_ms=%d",
            result.model,
            result.finish_reason,
            result.usage.input_tokens if result.usage else None,
            result.usage.output_tokens if result.usage else None,
            (time.perf_counter() - started) * 1000,
        )
        if self._log_content:
            logger.debug("Ollama response content=%s", result.content)
        return result

    @staticmethod
    def _map_status_error(response: httpx.Response, model: str) -> AppError:
        # Ollama's error text is logged (it never contains the prompt), never returned.
        try:
            detail = str(response.json().get("error", ""))[:300]
        except (ValueError, AttributeError):
            detail = ""
        status = response.status_code
        logger.warning("Ollama returned HTTP %s: %s", status, detail)
        if status == 404 or "not found" in detail.lower():
            return ProviderError(
                f"The Ollama server does not have model '{model}'. Pull it with "
                f"'ollama pull {model}' or change OLLAMA_MODEL.",
                code="provider_model_not_found",
            )
        if status in (400, 422):
            return ProviderRequestRejectedError(details={"provider_status": status})
        if status == 503:  # Ollama's request queue is full (OLLAMA_MAX_QUEUE)
            return ProviderUnavailableError("The Ollama server is busy. Retry shortly.")
        return ProviderUnavailableError(
            "The Ollama server failed to run the model (for example, not enough memory). "
            "See the Ollama server log."
        )

    @staticmethod
    def _to_result(response: httpx.Response, requested_model: str) -> ChatResult:
        def invalid(reason: str) -> ProviderError:
            logger.warning("Unexpected Ollama response: %s", reason)
            return ProviderError(
                "The Ollama server returned an unexpected response.",
                code="provider_invalid_response",
            )

        try:
            body = response.json()
        except ValueError:
            raise invalid("body is not JSON") from None
        if not isinstance(body, dict):
            raise invalid("body is not a JSON object")
        if body.get("error"):
            raise invalid("error field in a 200 response")
        message = body.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise invalid("missing message.content")
        if body.get("done") is False:
            raise invalid("incomplete (done=false) non-streaming response")

        done_reason = body.get("done_reason") or "stop"
        prompt_tokens = _non_negative_int(body.get("prompt_eval_count"))
        output_tokens = _non_negative_int(body.get("eval_count"))
        usage = None
        if prompt_tokens is not None or output_tokens is not None:
            # Ollama omits prompt_eval_count when the prompt was served from its cache.
            usage = ChatUsage(
                input_tokens=prompt_tokens or 0,
                output_tokens=output_tokens or 0,
                total_tokens=(prompt_tokens or 0) + (output_tokens or 0),
            )
        return ChatResult(
            id=f"ollama-{uuid.uuid4().hex}",  # Ollama responses carry no id
            model=str(body.get("model") or requested_model),
            content=message["content"],
            finish_reason=_OLLAMA_FINISH_REASONS.get(done_reason, str(done_reason)),
            usage=usage,
        )
