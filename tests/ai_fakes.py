"""Deterministic fakes for AI services. No model downloads, no network."""

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.ai.classification import TextClassificationService
from app.ai.llm import ChatMessage, ChatResult, ChatUsage


class FakeEmbeddingBackend:
    """Hash-seeded vectors: same text -> same vector; records every encode call."""

    def __init__(self, dimension: int = 8, model_name: str = "fake-embedder") -> None:
        self.model_name = model_name
        self._dimension = dimension
        self.calls: list[dict[str, Any]] = []

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: list[str], *, batch_size: int, normalize: bool) -> np.ndarray:
        self.calls.append({"n": len(texts), "batch_size": batch_size, "normalize": normalize})
        rows = []
        for text in texts:
            seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
            vector = np.random.default_rng(seed).normal(size=self._dimension)
            if normalize:
                vector = vector / np.linalg.norm(vector)
            rows.append(vector)
        return np.asarray(rows, dtype=np.float32)


class FakeEncoding:
    name = "fake_bpe"

    def encode(self, text: str, *, disallowed_special: Any = ()) -> list[int]:
        return list(range(len(text.split())))


class FakeInference:
    """Stands in for TransformerInferenceService.run()."""

    def __init__(self, output: Any = None) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def run(self, task: str, model_name: str, inputs: Any, **kwargs: Any) -> Any:
        self.calls.append({"task": task, "model": model_name, "inputs": inputs, **kwargs})
        if self.output is not None:
            return self.output
        top_k = kwargs.get("top_k", 1)
        rows = []
        for text in inputs:
            positive = 0.9 if "good" in text.lower() else 0.2
            row = [
                {"label": "POSITIVE", "score": positive},
                {"label": "NEGATIVE", "score": 1 - positive},
            ]
            rows.append(sorted(row, key=lambda d: -d["score"])[:top_k])
        return rows


def fake_classifier(**kwargs: Any) -> TextClassificationService:
    return TextClassificationService(
        model_name="fake-sentiment",
        inference=FakeInference(**kwargs),  # type: ignore[arg-type]
    )


@dataclass
class FakeChat:
    default_model: str = "fake-llm"
    reply: str = "fake reply"
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
            }
        )
        if self.error is not None:
            raise self.error
        return ChatResult(
            id=f"resp_{len(self.calls)}",
            model=model or self.default_model,
            content=f"{self.reply} #{len(self.calls)}",
            finish_reason="stop",
            usage=ChatUsage(input_tokens=10, output_tokens=3, total_tokens=13),
        )
