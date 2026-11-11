"""Evaluate the configured sentiment classifier on a labelled Hugging Face dataset.

Uses `datasets` to fetch data and `evaluate` for metrics (both in the "nlp" extra).
Downloads the dataset (SST-2 validation is ~100 KB) and metric scripts on first run.

Usage: python scripts/evaluate_classifier.py [--dataset stanfordnlp/sst2]
           [--split "validation[:200]"] [--text-column sentence] [--label-column label]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.container import AIServices
from app.ai.optional import require
from app.core.config import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="stanfordnlp/sst2")
    parser.add_argument("--split", default="validation[:200]")
    parser.add_argument("--text-column", default="sentence")
    parser.add_argument("--label-column", default="label")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    datasets = require("datasets", "Classifier evaluation")
    evaluate = require("evaluate", "Classifier evaluation")

    data = datasets.load_dataset(args.dataset, split=args.split)
    label_names = data.features[args.label_column].names  # e.g. ["negative", "positive"]

    ai = AIServices(load_settings())
    classifier = ai.text_classification
    predictions = []
    texts = data[args.text_column]
    for start in range(0, len(texts), args.batch_size):
        result = classifier.classify(texts[start : start + args.batch_size])
        for labels in result.labels:
            predicted = labels[0].label.lower()
            predictions.append(label_names.index(predicted))
    ai.shutdown()

    metrics = evaluate.combine(["accuracy", "f1"])
    scores = metrics.compute(predictions=predictions, references=data[args.label_column])
    print(f"Model:   {classifier.model_name}")
    print(f"Data:    {args.dataset} [{args.split}] n={len(predictions)}")
    for name, value in scores.items():
        print(f"{name:>8}: {value:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
