"""LLM chat completion behind a provider-neutral interface (`ChatService`), implemented for
a local Ollama server (`/api/chat`). No hosted provider and no API key is involved.

To add another local backend later, implement `ChatService.complete` and select it in
`app.ai.container.AIServices.chat_service`; routes and workflows depend only on the protocol.

Privacy default: prompts and completions are never logged unless LLM_LOG_CONTENT=true.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from app.ai.tokens import TokenCounter
from app.core.exceptions import (
    AppError,
    DataValidationError,
    ProviderError,
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


# Ollama "done_reason" -> this API's finish_reason vocabulary.
_OLLAMA_FINISH_REASONS = {"stop": "stop", "length": "max_output_tokens"}


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class OllamaChatService:
    """Chat completion against a local Ollama server (`POST /api/chat`, non-streaming).

    No API key is involved. Request validation (allow-list, message, character and token
    limits) runs before any call, and failures map to client-safe provider error codes.
    Prompt/response text is never logged unless log_content.
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
        num_ctx: int | None = None,
        num_thread: int | None = None,
        keep_alive: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.default_model = default_model
        self._num_ctx = num_ctx
        self._num_thread = num_thread
        self._keep_alive = keep_alive
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

    def health(self, timeout_seconds: float = 2.0) -> dict[str, Any]:
        """Is the server reachable, and is the default model pulled? Never raises."""
        try:
            response = self._client.get("/api/tags", timeout=timeout_seconds)
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.info("Ollama health check failed: %s", type(exc).__name__)
            return {"reachable": False, "model_available": False}
        if response.status_code != 200:
            return {"reachable": False, "model_available": False}
        try:
            names = {
                str(m.get("name") or m.get("model"))
                for m in response.json().get("models", [])
                if isinstance(m, dict)
            }
        except (ValueError, AttributeError):
            names = set()
        wanted = self.default_model
        # "llama3.2" and "llama3.2:latest" name the same model.
        available = wanted in names or (":" not in wanted and f"{wanted}:latest" in names)
        return {"reachable": True, "model_available": available}

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
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx
        if self._num_thread is not None:
            options["num_thread"] = self._num_thread
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": options,
        }
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive
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
