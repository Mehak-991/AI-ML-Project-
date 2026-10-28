import sys
import time

import numpy as np
import pytest

from app.ai.classification import TextClassificationService
from app.ai.embeddings import EmbeddingService, SentenceTransformerBackend
from app.ai.model_cache import ModelCache
from app.ai.runtime import InferenceExecutor
from app.ai.tokens import EstimatedEncoding, TokenCounter, load_tiktoken_encoding
from app.ai.transformer_inference import TransformerInferenceService
from app.core.exceptions import (
    DataValidationError,
    InferenceTimeoutError,
    ModelLoadError,
    OptionalDependencyMissingError,
)
from tests.ai_fakes import FakeEmbeddingBackend, FakeEncoding, FakeInference, fake_classifier


@pytest.fixture
def executor():
    executor = InferenceExecutor(max_workers=2, timeout_seconds=5)
    yield executor
    executor.shutdown()


def make_embedding_service(executor, backend=None, **overrides) -> EmbeddingService:
    backend = backend or FakeEmbeddingBackend(dimension=8)
    options = {"batch_size": 4, "max_texts": 20, "max_chars": 50} | overrides
    return EmbeddingService(
        model_name=backend.model_name,
        backend_factory=lambda: backend,
        cache=ModelCache(),
        executor=executor,
        **options,
    )


# --- embeddings ----------------------------------------------------------------------


def test_embedding_dimensions_and_order(executor) -> None:
    service = make_embedding_service(executor)
    result = service.embed(["alpha", "beta", "alpha"])
    assert result.dimension == 8
    assert len(result.vectors) == 3
    assert all(len(v) == 8 for v in result.vectors)
    assert result.vectors[0] == result.vectors[2]  # deterministic per text
    assert result.vectors[0] != result.vectors[1]
    assert all(isinstance(x, float) for x in result.vectors[0])


def test_embedding_batching(executor) -> None:
    backend = FakeEmbeddingBackend()
    service = make_embedding_service(executor, backend, batch_size=4)
    service.embed([f"text {i}" for i in range(10)])
    assert [c["n"] for c in backend.calls] == [4, 4, 2]
    assert service.batches_for(10) == 3


def test_embedding_normalization_flag(executor) -> None:
    backend = FakeEmbeddingBackend()
    service = make_embedding_service(executor, backend)
    normalized = service.embed(["x"], normalize=True).vectors[0]
    raw = service.embed(["x"], normalize=False).vectors[0]
    assert np.linalg.norm(normalized) == pytest.approx(1.0, abs=1e-5)
    assert np.linalg.norm(raw) != pytest.approx(1.0, abs=1e-3)
    assert [c["normalize"] for c in backend.calls] == [True, False]


def test_backend_loaded_once_across_requests(executor) -> None:
    loads = []

    def factory():
        loads.append(1)
        return FakeEmbeddingBackend()

    service = EmbeddingService(
        model_name="m", backend_factory=factory, cache=ModelCache(), executor=executor
    )
    for _ in range(3):
        service.embed(["hello"])
    assert len(loads) == 1


@pytest.mark.parametrize(
    ("texts", "message"),
    [
        ([], "At least one"),
        (["ok"] * 21, "At most 20"),
        (["ok", "   "], "Invalid input"),
        (["x" * 51], "Invalid input"),
    ],
)
def test_embedding_input_validation(executor, texts, message) -> None:
    with pytest.raises(DataValidationError, match=message):
        make_embedding_service(executor).embed(texts)


def test_expected_dimension_mismatch(executor) -> None:
    service = make_embedding_service(executor, expected_dimension=384)
    with pytest.raises(ModelLoadError, match=r"8-dimensional.*EMBEDDING_DIMENSION=384"):
        service.embed(["hello"])


def test_expected_dimension_match(executor) -> None:
    assert make_embedding_service(executor, expected_dimension=8).embed(["a"]).dimension == 8


class _BadShapeBackend(FakeEmbeddingBackend):
    def encode(self, texts, *, batch_size, normalize):
        return np.zeros((len(texts), self.dimension + 1), dtype=np.float32)


class _NanBackend(FakeEmbeddingBackend):
    def encode(self, texts, *, batch_size, normalize):
        return np.full((len(texts), self.dimension), np.nan, dtype=np.float32)


@pytest.mark.parametrize(
    ("backend", "message"), [(_BadShapeBackend(), "shape"), (_NanBackend(), "non-finite")]
)
def test_invalid_model_output(executor, backend, message) -> None:
    with pytest.raises(ModelLoadError, match=message):
        make_embedding_service(executor, backend).embed(["a"])


def test_embedding_model_load_failure(executor) -> None:
    def broken():
        raise OSError("model not found on hub")

    service = EmbeddingService(
        model_name="org/missing", backend_factory=broken, cache=ModelCache(), executor=executor
    )
    with pytest.raises(ModelLoadError, match="Could not load model"):
        service.embed(["a"])


def test_embedding_timeout() -> None:
    class SlowBackend(FakeEmbeddingBackend):
        def encode(self, texts, *, batch_size, normalize):
            time.sleep(0.5)
            return super().encode(texts, batch_size=batch_size, normalize=normalize)

    executor = InferenceExecutor(max_workers=1, timeout_seconds=0.05)
    with pytest.raises(InferenceTimeoutError):
        make_embedding_service(executor, SlowBackend()).embed(["a"])
    executor.shutdown()


def test_sentence_transformers_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(OptionalDependencyMissingError, match=r"\.\[nlp\]"):
        SentenceTransformerBackend("any/model", "cpu")


def test_sentence_transformer_backend_with_fake_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the real backend class against a stub library (no download)."""
    created = {}

    class StubModel:
        def __init__(self, name, **kwargs):
            created.update(name=name, **kwargs)

        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, texts, **kwargs):
            created["encode_kwargs"] = kwargs
            return np.ones((len(texts), 3))

    stub = type(sys)("sentence_transformers")
    stub.SentenceTransformer = StubModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub)

    backend = SentenceTransformerBackend("org/model", "cpu")
    assert backend.dimension == 3
    assert created["trust_remote_code"] is False
    assert backend.encode(["a", "b"], batch_size=2, normalize=True).dtype == np.float32
    assert created["encode_kwargs"]["normalize_embeddings"] is True


# --- transformer inference / classification ------------------------------------------


def test_classification_results_sorted_and_truncated() -> None:
    service = fake_classifier()
    result = service.classify(["A good day", "bad news"], top_k=2)
    assert result.task == "sentiment-analysis"
    assert [x.label for x in result.labels[0]] == ["POSITIVE", "NEGATIVE"]
    assert [x.label for x in result.labels[1]] == ["NEGATIVE", "POSITIVE"]
    assert result.labels[0][0].score == pytest.approx(0.9)
    assert len(service.classify(["good"], top_k=1).labels[0]) == 1


def test_classification_accepts_flat_pipeline_output() -> None:
    service = fake_classifier(output=[{"label": "POSITIVE", "score": 0.7}])
    assert service.classify(["x"]).labels[0][0].label == "POSITIVE"


@pytest.mark.parametrize("output", [[], [{"oops": 1}], "nonsense"])
def test_classification_rejects_unexpected_output(output) -> None:
    with pytest.raises(ModelLoadError):
        fake_classifier(output=output).classify(["x"])


def test_classification_passes_truncation_and_top_k() -> None:
    inference = FakeInference()
    service = TextClassificationService(model_name="m", inference=inference)  # type: ignore[arg-type]
    service.classify(["hello"], top_k=2)
    assert inference.calls[0]["truncation"] is True
    assert inference.calls[0]["top_k"] == 2
    assert inference.calls[0]["task"] == "text-classification"


def test_classification_validation() -> None:
    with pytest.raises(DataValidationError):
        fake_classifier().classify([""])


def test_transformer_pipeline_cached_and_device_resolved_lazily(executor) -> None:
    loads, devices = [], []

    def loader(task, model, device):
        loads.append((task, model, device))
        return lambda inputs, **kw: [{"label": "X", "score": 1.0}] * len(inputs)

    def device_resolver():
        devices.append(1)
        return "cpu"

    service = TransformerInferenceService(
        cache=ModelCache(), executor=executor, device_resolver=device_resolver, loader=loader
    )
    assert devices == []  # nothing resolved/loaded at construction
    for _ in range(3):
        service.run("text-classification", "m", ["a"])
    assert loads == [("text-classification", "m", "cpu")]
    with pytest.raises(ValueError, match="Unsupported task"):
        service.run("text-generation", "m", ["a"])


def test_transformers_missing_surfaces_as_503(monkeypatch: pytest.MonkeyPatch, executor) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    service = TransformerInferenceService(
        cache=ModelCache(), executor=executor, device_resolver=lambda: "cpu"
    )
    with pytest.raises(OptionalDependencyMissingError, match="PyTorch"):
        service.run("text-classification", "m", ["a"])


# --- tokens --------------------------------------------------------------------------


def test_token_count_with_encoding() -> None:
    counter = TokenCounter("gpt-test", loader=lambda model: FakeEncoding())
    counted = counter.count("one two three")
    assert (counted.tokens, counted.encoding, counted.approximate) == (3, "fake_bpe", False)


def test_token_count_approximate_fallback() -> None:
    counter = TokenCounter("gpt-test", loader=lambda model: None)
    counted = counter.count("x" * 10)
    assert (counted.tokens, counted.encoding, counted.approximate) == (3, "approximate", True)
    assert counter.count("").tokens == 0


def test_message_token_count_includes_overhead() -> None:
    counter = TokenCounter("gpt-test", loader=lambda model: FakeEncoding())
    counted = counter.count_messages([("user", "hello there"), ("assistant", "hi")])
    # 3 priming + per message (3 overhead + role + content)
    assert counted.tokens == 3 + (3 + 1 + 2) + (3 + 1 + 1)


def test_encoding_loaded_once_per_model() -> None:
    loads = []
    counter = TokenCounter("a", loader=lambda model: loads.append(model) or FakeEncoding())
    counter.count("x")
    counter.count("y")
    counter.count("z", model="b")
    assert loads == ["a", "b"]


def test_tiktoken_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    assert load_tiktoken_encoding("gpt-4o") is None


def test_tiktoken_download_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = type(sys)("tiktoken")

    def boom(*args, **kwargs):
        raise OSError("network unreachable")

    stub.encoding_for_model = boom
    stub.get_encoding = boom
    monkeypatch.setitem(sys.modules, "tiktoken", stub)
    assert load_tiktoken_encoding("gpt-4o") is None


def test_tiktoken_unknown_model_uses_default_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = type(sys)("tiktoken")

    def unknown(model):
        raise KeyError(model)

    stub.encoding_for_model = unknown
    stub.get_encoding = lambda name: FakeEncoding()
    monkeypatch.setitem(sys.modules, "tiktoken", stub)
    encoding = load_tiktoken_encoding("brand-new-model")
    # Unknown models (e.g. Llama via Ollama) get the default BPE, flagged as an estimate.
    assert isinstance(encoding, EstimatedEncoding)
    assert encoding.name == "fake_bpe"
    counter = TokenCounter("brand-new-model", loader=load_tiktoken_encoding)
    assert counter.count("one two").approximate is True
