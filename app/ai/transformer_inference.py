"""Cached Hugging Face `pipeline` loading and time-bounded execution."""

from collections.abc import Callable
from typing import Any

from app.ai.model_cache import ModelCache
from app.ai.optional import require
from app.ai.runtime import InferenceExecutor

# Tasks this service will load. Extend deliberately; each new task needs output handling.
SUPPORTED_TASKS = frozenset({"text-classification"})

PipelineLoader = Callable[[str, str], Callable[..., Any]]


def load_hf_pipeline(task: str, model_name: str, device: str) -> Callable[..., Any]:
    require("torch", "Transformer inference")
    transformers = require("transformers", "Transformer inference")
    return transformers.pipeline(task, model=model_name, device=device, trust_remote_code=False)


class TransformerInferenceService:
    def __init__(
        self,
        *,
        cache: ModelCache,
        executor: InferenceExecutor,
        device_resolver: Callable[[], str],
        loader: Callable[[str, str, str], Callable[..., Any]] = load_hf_pipeline,
    ) -> None:
        self._cache = cache
        self._executor = executor
        self._device_resolver = device_resolver
        self._loader = loader

    def pipeline(self, task: str, model_name: str) -> Callable[..., Any]:
        if task not in SUPPORTED_TASKS:
            raise ValueError(f"Unsupported task '{task}'.")
        return self._cache.get_or_load(
            ("pipeline", task, model_name),
            lambda: self._loader(task, model_name, self._device_resolver()),
        )

    def run(self, task: str, model_name: str, inputs: Any, **kwargs: Any) -> Any:
        pipe = self.pipeline(task, model_name)
        return self._executor.run(lambda: pipe(inputs, **kwargs))
