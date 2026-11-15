"""Per-application container that builds AI services lazily and shares heavy state.

One instance lives on `app.state.ai`. Nothing here imports an optional package
or loads a model until a service is first used, so startup stays fast and works
without the AI extras or an API key.
"""

import threading
from functools import cached_property
from typing import Any

from app.ai.classification import TextClassificationService
from app.ai.embeddings import EmbeddingService, SentenceTransformerBackend
from app.ai.llm import ChatLimits, ChatService, OllamaChatService
from app.ai.model_cache import ModelCache
from app.ai.optional import EXTRA_FOR_MODULE, is_available
from app.ai.runtime import InferenceExecutor, configure_hf_environment, resolve_device
from app.ai.tokens import TokenCounter
from app.ai.transformer_inference import TransformerInferenceService
from app.ai.workflows.text_analysis import TextAnalysisWorkflow
from app.core.config import Settings


class AIServices:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        configure_hf_environment(settings)
        self.model_cache = ModelCache(settings.AI_MAX_LOADED_MODELS)
        self.executor = InferenceExecutor(
            settings.AI_MAX_CONCURRENT_INFERENCES, settings.AI_INFERENCE_TIMEOUT_SECONDS
        )
        # Token counts for local Llama-family models are estimates (see app.ai.tokens).
        self.token_counter = TokenCounter(settings.active_llm_model)
        self._lock = threading.Lock()
        self._chat: ChatService | None = None
        self._device: str | None = None

    def device(self) -> str:
        if self._device is None:
            self._device = resolve_device(self.settings.AI_DEVICE)
        return self._device

    @cached_property
    def transformer_inference(self) -> TransformerInferenceService:
        return TransformerInferenceService(
            cache=self.model_cache, executor=self.executor, device_resolver=self.device
        )

    @cached_property
    def embedding_service(self) -> EmbeddingService:
        s = self.settings
        return EmbeddingService(
            model_name=s.EMBEDDING_MODEL,
            backend_factory=lambda: SentenceTransformerBackend(s.EMBEDDING_MODEL, self.device()),
            cache=self.model_cache,
            executor=self.executor,
            batch_size=s.EMBEDDING_BATCH_SIZE,
            max_texts=s.EMBEDDING_MAX_TEXTS,
            max_chars=s.EMBEDDING_MAX_TEXT_CHARS,
            expected_dimension=s.EMBEDDING_DIMENSION,
        )

    @cached_property
    def text_classification(self) -> TextClassificationService:
        s = self.settings
        return TextClassificationService(
            model_name=s.CLASSIFIER_MODEL,
            inference=self.transformer_inference,
            max_texts=s.CLASSIFIER_MAX_TEXTS,
            max_chars=s.CLASSIFIER_MAX_TEXT_CHARS,
        )

    def _chat_limits(self) -> ChatLimits:
        s = self.settings
        return ChatLimits(
            max_messages=s.LLM_MAX_MESSAGES,
            max_input_chars=s.LLM_MAX_INPUT_CHARS,
            max_input_tokens=s.LLM_MAX_INPUT_TOKENS,
            max_output_tokens=s.LLM_MAX_OUTPUT_TOKENS,
            default_output_tokens=s.LLM_DEFAULT_OUTPUT_TOKENS,
        )

    def chat_service(self) -> ChatService:
        """The configured local LLM (built once, reused across requests).

        Only Ollama is supported; no API key is needed. Whether the server is up shows on
        first use (503 provider_unavailable) and in the readiness probe.
        """
        if self._chat is not None:
            return self._chat
        s = self.settings
        with self._lock:
            if self._chat is None:
                self._chat = OllamaChatService(
                    base_url=s.OLLAMA_BASE_URL,
                    default_model=s.OLLAMA_MODEL,
                    allowed_models=s.allowed_llm_models,
                    limits=self._chat_limits(),
                    token_counter=self.token_counter,
                    timeout_seconds=s.OLLAMA_TIMEOUT_SECONDS,
                    log_content=s.LLM_LOG_CONTENT,
                    num_ctx=s.OLLAMA_NUM_CTX,
                    num_thread=s.OLLAMA_NUM_THREAD,
                    keep_alive=s.OLLAMA_KEEP_ALIVE,
                )
        return self._chat

    def llm_health(self) -> dict[str, Any]:
        """Reachability of the local LLM server and its default model. Never raises."""
        chat = self.chat_service()
        health = getattr(chat, "health", None)
        if not callable(health):
            return {"reachable": None, "model_available": None}
        return health()

    def text_analysis(self, *, include_sentiment: bool) -> TextAnalysisWorkflow:
        chat = self.chat_service()
        return TextAnalysisWorkflow(
            chat=chat,
            token_counter=self.token_counter,
            classifier_factory=(lambda: self.text_classification) if include_sentiment else None,
        )

    def status(self) -> dict[str, Any]:
        s = self.settings
        return {
            "packages": {module: is_available(module) for module in sorted(EXTRA_FOR_MODULE)},
            "llm": {
                "provider": s.LLM_PROVIDER,
                # Local Ollama needs no key; whether the server is up shows on first use.
                "configured": True,
                "requires_api_key": False,
                "default_model": s.active_llm_model,
                "allowed_models": s.allowed_llm_models,
            },
            "embeddings": {"model": s.EMBEDDING_MODEL, "expected_dimension": s.EMBEDDING_DIMENSION},
            "classifier": {"model": s.CLASSIFIER_MODEL},
            "device_preference": s.AI_DEVICE,
            "downloads_allowed": s.AI_ALLOW_MODEL_DOWNLOADS,
            "loaded_models": self.model_cache.loaded(),
        }

    def shutdown(self) -> None:
        self.executor.shutdown()
        self.model_cache.clear()
        with self._lock:
            chat, self._chat = self._chat, None
        close = getattr(chat, "close", None)
        if callable(close):  # releases the Ollama HTTP connection pool
            close()
