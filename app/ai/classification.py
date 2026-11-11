"""Baseline NLP task: sentiment classification with a pretrained transformer.

Default model: distilbert/distilbert-base-uncased-finetuned-sst-2-english
(binary POSITIVE/NEGATIVE, English, ~270 MB). Swap via CLASSIFIER_MODEL for any
Hugging Face `text-classification` model.
"""

from dataclasses import dataclass
from typing import Any

from app.ai.transformer_inference import TransformerInferenceService
from app.ai.validation import validate_texts
from app.core.exceptions import ModelLoadError

TASK = "text-classification"


@dataclass(frozen=True)
class LabelScore:
    label: str
    score: float


@dataclass(frozen=True)
class ClassificationResult:
    model: str
    task: str
    labels: list[list[LabelScore]]


def _normalize_output(raw: Any, n_texts: int) -> list[list[dict[str, Any]]]:
    """Pipelines return list[dict] or list[list[dict]] depending on version and top_k."""
    if not isinstance(raw, list) or len(raw) != n_texts:
        raise ModelLoadError("The classification model returned an unexpected output shape.")
    rows = [item if isinstance(item, list) else [item] for item in raw]
    for row in rows:
        if not all(isinstance(d, dict) and "label" in d and "score" in d for d in row):
            raise ModelLoadError("The classification model returned an unexpected output format.")
    return rows


class TextClassificationService:
    def __init__(
        self,
        *,
        model_name: str,
        inference: TransformerInferenceService,
        max_texts: int = 64,
        max_chars: int = 4_000,
    ) -> None:
        self.model_name = model_name
        self._inference = inference
        self.max_texts = max_texts
        self.max_chars = max_chars

    def classify(self, texts: list[str], *, top_k: int = 1) -> ClassificationResult:
        texts = validate_texts(texts, max_texts=self.max_texts, max_chars=self.max_chars)
        raw = self._inference.run(TASK, self.model_name, texts, top_k=top_k, truncation=True)
        labels = [
            sorted(
                (LabelScore(str(d["label"]), round(float(d["score"]), 6)) for d in row),
                key=lambda item: item.score,
                reverse=True,
            )[:top_k]
            for row in _normalize_output(raw, len(texts))
        ]
        return ClassificationResult(model=self.model_name, task="sentiment-analysis", labels=labels)
