"""Local NLP demo: semantic similarity with embeddings + sentiment classification.

Runs entirely on this machine (no API key). Requires PyTorch + `pip install -e ".[nlp]"`;
the first run downloads ~360 MB of models (see scripts/download_models.py).

Usage: python scripts/nlp_demo.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.container import AIServices
from app.core.config import load_settings
from app.core.exceptions import AppError

SENTENCES = [
    "The new update made the app much faster.",
    "Performance improved a lot after the latest release.",
    "I could not log in and support never answered.",
    "The weather is sunny today.",
]


def main() -> int:
    ai = AIServices(load_settings())
    try:
        embeddings = ai.embedding_service.embed(SENTENCES, normalize=True)
        vectors = np.asarray(embeddings.vectors)
        similarity = vectors @ vectors.T  # cosine similarity (vectors are L2-normalised)
        print(f"Embedding model: {embeddings.model}  dimension={embeddings.dimension}\n")
        print("Cosine similarity:")
        for i, sentence in enumerate(SENTENCES):
            scores = "  ".join(f"{s:5.2f}" for s in similarity[i])
            print(f"  [{i}] {scores}   {sentence}")

        print("\nSentiment:")
        classified = ai.text_classification.classify(SENTENCES)
        for sentence, labels in zip(SENTENCES, classified.labels, strict=True):
            print(f"  {labels[0].label:<9} {labels[0].score:.3f}  {sentence}")
    except AppError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1
    finally:
        ai.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
