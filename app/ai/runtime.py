"""Device selection, Hugging Face environment setup, and bounded inference execution."""

import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Literal, TypeVar

from app.ai.optional import require
from app.core.config import Settings
from app.core.exceptions import InferenceTimeoutError, ModelLoadError

logger = logging.getLogger(__name__)

T = TypeVar("T")
DevicePreference = Literal["auto", "cpu", "cuda", "mps"]


def resolve_device(preference: DevicePreference) -> str:
    """Pick the torch device. 'auto' prefers CUDA, then Apple MPS, then CPU."""
    if preference == "cpu":
        return "cpu"
    torch = require("torch", "Local model inference")
    cuda = bool(torch.cuda.is_available())
    mps_backend = getattr(torch.backends, "mps", None)
    mps = bool(mps_backend and mps_backend.is_available())
    if preference == "cuda" and not cuda:
        raise ModelLoadError(
            "AI_DEVICE=cuda but CUDA is not available to PyTorch. Install a CUDA build of "
            "PyTorch or set AI_DEVICE=cpu."
        )
    if preference == "mps" and not mps:
        raise ModelLoadError("AI_DEVICE=mps but Apple MPS is not available. Set AI_DEVICE=cpu.")
    if preference in ("cuda", "mps"):
        return preference
    return "cuda" if cuda else "mps" if mps else "cpu"


def configure_hf_environment(settings: Settings) -> None:
    """Set Hugging Face cache/offline variables before transformers is first imported.

    Existing environment variables win, so operators can still override them.
    """
    if settings.AI_MODEL_CACHE_DIR is not None:
        os.environ.setdefault("HF_HOME", str(settings.AI_MODEL_CACHE_DIR.resolve()))
    if not settings.AI_ALLOW_MODEL_DOWNLOADS:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


class InferenceExecutor:
    """A bounded thread pool that applies a timeout to model calls.

    The pool size caps concurrent heavy inferences. Python threads cannot be
    killed, so a timed-out call keeps running in the background until it ends;
    the caller gets a 504 immediately and the slot is freed when it completes.
    """

    def __init__(self, max_workers: int, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_workers = max_workers
        self._pool: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()

    def _get_pool(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._pool is None:  # created lazily; recreated after shutdown()
                self._pool = ThreadPoolExecutor(
                    max_workers=self.max_workers, thread_name_prefix="ai-infer"
                )
            return self._pool

    def run(self, fn: Callable[[], T], *, timeout: float | None = None) -> T:
        future = self._get_pool().submit(fn)
        limit = timeout if timeout is not None else self.timeout_seconds
        try:
            return future.result(timeout=limit)
        except FutureTimeoutError:
            future.cancel()
            raise InferenceTimeoutError(
                f"Model inference did not finish within {limit:g} seconds."
            ) from None

    def shutdown(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
