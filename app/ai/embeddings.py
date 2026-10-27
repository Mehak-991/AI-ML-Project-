"""Sentence embeddings with Sentence Transformers behind a small interface."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.ai.model_cache import ModelCache
from app.ai.optional import require
from app.ai.runtime import InferenceExecutor
from app.ai.validation import validate_texts
from app.core.exceptions import ModelLoadError


class EmbeddingBackend(Protocol):
    model_name: str

    @property
    def dimension(self) -> int: ...

    def encode(self, texts: list[str], *, batch_size: int, normalize: bool) -> np.ndarray: ...


class SentenceTransformerBackend:
    """Loads a Sentence Transformers model once; `trust_remote_code` is always off."""

    def __init__(self, model_name: str, device: str) -> None:
        module = require("sentence_transformers", "Text embeddings")
        self.model_name = model_name
        self.device = device
        self._model = module.SentenceTransformer(model_name, device=device, trust_remote_code=False)
        getter = getattr(self._model, "get_sentence_embedding_dimension", None)
        dimension = getter() if getter else None
        if not dimension:  # some models only reveal it after a forward pass
            dimension = int(
                self.encode(["dimension probe"], batch_size=1, normalize=False).shape[1]
            )
        self._dimension = int(dimension)

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: list[str], *, batch_size: int, normalize: bool) -> np.ndarray:
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


@dataclass(frozen=True)
class EmbeddingResult:
    model: str
    dimension: int
    vectors: list[list[float]]


class EmbeddingService:
    def __init__(
        self,
        *,
        model_name: str,
        backend_factory: Callable[[], EmbeddingBackend],
        cache: ModelCache,
        executor: InferenceExecutor,
        batch_size: int = 32,
        max_texts: int = 128,
        max_chars: int = 8_000,
        expected_dimension: int | None = None,
    ) -> None:
        self.model_name = model_name
        self._backend_factory = backend_factory
        self._cache = cache
        self._executor = executor
        self.batch_size = batch_size
        self.max_texts = max_texts
        self.max_chars = max_chars
        self.expected_dimension = expected_dimension

    def backend(self) -> EmbeddingBackend:
        backend = self._cache.get_or_load(("embedding", self.model_name), self._backend_factory)
        if self.expected_dimension is not None and backend.dimension != self.expected_dimension:
            raise ModelLoadError(
                f"Model '{self.model_name}' produces {backend.dimension}-dimensional vectors but "
                f"EMBEDDING_DIMENSION={self.expected_dimension}. Update one of them.",
                details={"model_dimension": backend.dimension},
            )
        return backend

    def embed(self, texts: list[str], *, normalize: bool = True) -> EmbeddingResult:
        texts = validate_texts(texts, max_texts=self.max_texts, max_chars=self.max_chars)
        backend = self.backend()
        dimension = backend.dimension
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            array = self._executor.run(
                lambda batch=batch: backend.encode(
                    batch, batch_size=self.batch_size, normalize=normalize
                )
            )
            array = np.asarray(array)
            if array.shape != (len(batch), dimension):
                raise ModelLoadError(
                    f"Embedding model returned shape {array.shape}; "
                    f"expected ({len(batch)}, {dimension})."
                )
            if not np.isfinite(array).all():
                raise ModelLoadError("Embedding model returned non-finite values.")
            vectors.extend(array.astype(float).tolist())
        return EmbeddingResult(model=self.model_name, dimension=dimension, vectors=vectors)

    def batches_for(self, n_texts: int) -> int:
        return math.ceil(n_texts / self.batch_size)
