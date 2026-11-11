"""Process-wide cache so large models are loaded once, not per request."""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

from app.core.exceptions import AppError, ModelLoadError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ModelCache:
    """Thread-safe LRU cache of loaded models.

    Concurrent requests for the same key wait on a per-key lock, so a model is
    loaded exactly once even under load. Failed loads are not cached.
    """

    def __init__(self, max_entries: int = 3) -> None:
        self.max_entries = max_entries
        self._models: OrderedDict[Hashable, Any] = OrderedDict()
        self._load_seconds: dict[Hashable, float] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[Hashable, threading.Lock] = {}

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> T:
        with self._lock:
            if key in self._models:
                self._models.move_to_end(key)
                return self._models[key]
            key_lock = self._key_locks.setdefault(key, threading.Lock())

        with key_lock:
            with self._lock:
                if key in self._models:  # loaded by another thread while we waited
                    self._models.move_to_end(key)
                    return self._models[key]
            started = time.perf_counter()
            try:
                model = loader()
            except AppError:
                raise
            except Exception as exc:  # includes OSError, MemoryError-adjacent runtime errors
                logger.warning("Loading model %s failed: %s", key, type(exc).__name__)
                raise ModelLoadError(
                    f"Could not load model {key!r}. Check the model name, disk space, network "
                    "access (or AI_ALLOW_MODEL_DOWNLOADS) and the server log.",
                    details={"model": str(key)},
                ) from exc
            elapsed = time.perf_counter() - started
            logger.info("Loaded model %s in %.1fs", key, elapsed)
            with self._lock:
                self._models[key] = model
                self._load_seconds[key] = round(elapsed, 3)
                while len(self._models) > self.max_entries:
                    evicted, _ = self._models.popitem(last=False)
                    self._load_seconds.pop(evicted, None)
                    logger.info("Evicted model %s from cache", evicted)
            return model

    def loaded(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"key": str(key), "load_seconds": self._load_seconds.get(key)}
                for key in self._models
            ]

    def __contains__(self, key: Hashable) -> bool:
        with self._lock:
            return key in self._models

    def clear(self) -> None:
        with self._lock:
            self._models.clear()
            self._load_seconds.clear()
