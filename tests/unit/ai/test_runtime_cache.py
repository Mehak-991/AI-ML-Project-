import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from app.ai.model_cache import ModelCache
from app.ai.optional import install_hint, is_available, require
from app.ai.runtime import InferenceExecutor, configure_hf_environment, resolve_device
from app.core.exceptions import (
    InferenceTimeoutError,
    ModelLoadError,
    OptionalDependencyMissingError,
)

# --- optional imports --------------------------------------------------------------


def test_require_missing_package_gives_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # simulate "not installed"
    with pytest.raises(OptionalDependencyMissingError) as exc_info:
        require("sentence_transformers", "Text embeddings")
    error = exc_info.value
    assert error.status_code == 503
    assert 'pip install -e ".[nlp]"' in error.message
    assert error.details["package"] == "sentence_transformers"


def test_torch_hint_points_to_pytorch_index() -> None:
    assert "download.pytorch.org/whl/cpu" in install_hint("torch")


def test_is_available() -> None:
    assert is_available("json")
    assert not is_available("definitely_not_a_real_package_xyz")


# --- model cache -------------------------------------------------------------------


def test_cache_loads_once_and_reuses() -> None:
    cache = ModelCache(max_entries=2)
    loads = []
    for _ in range(3):
        model = cache.get_or_load("a", lambda: loads.append(1) or object())
    assert len(loads) == 1
    assert cache.get_or_load("a", lambda: None) is model


def test_cache_loads_once_under_concurrency() -> None:
    cache = ModelCache()
    loads = []

    def slow_loader():
        loads.append(1)
        time.sleep(0.05)
        return object()

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(cache.get_or_load("k", slow_loader)))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(loads) == 1
    assert len({id(r) for r in results}) == 1


def test_cache_evicts_least_recently_used() -> None:
    cache = ModelCache(max_entries=2)
    cache.get_or_load("a", object)
    cache.get_or_load("b", object)
    cache.get_or_load("a", object)  # touch a
    cache.get_or_load("c", object)
    assert "a" in cache and "c" in cache and "b" not in cache
    assert [m["key"] for m in cache.loaded()] == ["a", "c"]


def test_cache_wraps_load_failures_and_does_not_cache_them() -> None:
    cache = ModelCache()

    def broken():
        raise OSError("disk full")

    with pytest.raises(ModelLoadError) as exc_info:
        cache.get_or_load(("embedding", "bad/model"), broken)
    assert "disk full" not in exc_info.value.message  # internals stay in the log
    assert ("embedding", "bad/model") not in cache
    assert cache.get_or_load(("embedding", "bad/model"), lambda: "ok") == "ok"


def test_cache_passes_app_errors_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "transformers", None)
    with pytest.raises(OptionalDependencyMissingError):
        ModelCache().get_or_load("x", lambda: require("transformers", "test"))


# --- executor ----------------------------------------------------------------------


def test_executor_returns_result() -> None:
    executor = InferenceExecutor(max_workers=1, timeout_seconds=5)
    assert executor.run(lambda: 42) == 42
    executor.shutdown()


def test_executor_times_out() -> None:
    executor = InferenceExecutor(max_workers=1, timeout_seconds=0.05)
    with pytest.raises(InferenceTimeoutError) as exc_info:
        executor.run(lambda: time.sleep(0.5))
    assert exc_info.value.status_code == 504
    executor.shutdown()


def test_executor_propagates_errors_and_recovers_after_shutdown() -> None:
    executor = InferenceExecutor(max_workers=1, timeout_seconds=5)
    with pytest.raises(ZeroDivisionError):
        executor.run(lambda: 1 / 0)
    executor.shutdown()
    assert executor.run(lambda: "again") == "again"
    executor.shutdown()


# --- device selection ----------------------------------------------------------------


def _fake_torch(cuda: bool, mps: bool):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


def test_cpu_device_needs_no_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    assert resolve_device("cpu") == "cpu"


@pytest.mark.parametrize(
    ("cuda", "mps", "expected"),
    [(True, True, "cuda"), (False, True, "mps"), (False, False, "cpu")],
)
def test_auto_device(monkeypatch: pytest.MonkeyPatch, cuda, mps, expected) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda, mps))
    assert resolve_device("auto") == expected


def test_requested_gpu_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(False, False))
    with pytest.raises(ModelLoadError, match="CUDA is not available"):
        resolve_device("cuda")
    with pytest.raises(ModelLoadError, match="MPS"):
        resolve_device("mps")


def test_auto_device_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(OptionalDependencyMissingError, match="PyTorch"):
        resolve_device("auto")


def test_configure_hf_environment(monkeypatch: pytest.MonkeyPatch, make_settings, tmp_path) -> None:
    for name in ("HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    configure_hf_environment(
        make_settings(AI_MODEL_CACHE_DIR=tmp_path / "hf", AI_ALLOW_MODEL_DOWNLOADS=False)
    )
    assert os.environ["HF_HOME"] == str((tmp_path / "hf").resolve())
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_namespace_directory_is_not_mistaken_for_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A plain folder named like a package (e.g. ./datasets) must not count as installed."""
    (tmp_path / "fake_ns_pkg_xyz").mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    assert not is_available("fake_ns_pkg_xyz")
    with pytest.raises(OptionalDependencyMissingError):
        require("fake_ns_pkg_xyz", "test")


def test_installed_namespace_package_is_detected() -> None:
    """langgraph 1.x ships as a namespace package; it must still count as installed."""
    pytest.importorskip("langgraph.graph")
    assert is_available("langgraph")
    require("langgraph.graph", "test")


def test_project_datasets_folder_is_not_huggingface_datasets() -> None:
    import importlib.metadata

    try:
        importlib.metadata.distribution("datasets")
        pytest.skip("Hugging Face datasets is installed")
    except importlib.metadata.PackageNotFoundError:
        pass
    assert not is_available("datasets")
