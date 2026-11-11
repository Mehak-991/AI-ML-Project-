"""Download the configured local models ahead of time (the API never does this at startup).

Usage: python scripts/download_models.py [--embedding] [--classifier]   (default: both)

Requires the optional extras: PyTorch + `pip install -e ".[nlp]"`.
Models are stored in AI_MODEL_CACHE_DIR (or ~/.cache/huggingface). Approximate sizes:
  sentence-transformers/all-MiniLM-L6-v2                      ~90 MB
  distilbert/distilbert-base-uncased-finetuned-sst-2-english  ~270 MB
Afterwards you can set AI_ALLOW_MODEL_DOWNLOADS=false to run fully offline.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.container import AIServices
from app.core.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding", action="store_true")
    parser.add_argument("--classifier", action="store_true")
    args = parser.parse_args()
    both = not (args.embedding or args.classifier)

    settings = load_settings()
    ai = AIServices(settings)
    print(f"Device: {ai.device()}")
    if both or args.embedding:
        started = time.perf_counter()
        backend = ai.embedding_service.backend()
        print(
            f"Embedding model ready: {settings.EMBEDDING_MODEL} "
            f"(dimension={backend.dimension}, {time.perf_counter() - started:.1f}s)"
        )
    if both or args.classifier:
        started = time.perf_counter()
        ai.transformer_inference.pipeline("text-classification", settings.CLASSIFIER_MODEL)
        print(
            f"Classifier ready: {settings.CLASSIFIER_MODEL} ({time.perf_counter() - started:.1f}s)"
        )
    ai.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
