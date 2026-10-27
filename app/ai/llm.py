"""LLM chat completion via the OpenAI Responses API, behind a provider-neutral interface.

Privacy defaults: prompts and completions are never logged unless
LLM_LOG_CONTENT=true, the API key is never logged, and requests are sent with
`store=False` so the provider does not retain them for later retrieval.
"""

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

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
