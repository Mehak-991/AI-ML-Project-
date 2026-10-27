"""Train a baseline model from a local CSV/XLSX file without the API or database.

Writes a joblib artifact to MODEL_DIR and prints its metrics. Useful for
experiments and CI; use the API to register models for serving.

Usage: python scripts/train_model.py datasets/examples/synthetic_classification.csv \
           --target label [--algorithm linear|random_forest] [--problem-type classification]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings  # noqa: E402
from app.ml.ingestion import detect_file_format, read_tabular_file  # noqa: E402
from app.ml.persistence import save_artifact  # noqa: E402
from app.ml.training import TrainingConfig, train_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--algorithm", choices=["linear", "random_forest"], default="linear")
    parser.add_argument("--problem-type", choices=["classification", "regression"])
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--validation-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()

    settings = load_settings()
    frame = read_tabular_file(
        args.path,
        detect_file_format(args.path.name),
        max_rows=settings.MAX_DATASET_ROWS,
        max_columns=settings.MAX_DATASET_COLUMNS,
    )
    result = train_model(
        frame,
        TrainingConfig(
            target_column=args.target,
            problem_type=args.problem_type,
            algorithm=args.algorithm,
            test_size=args.test_size,
            validation_size=args.validation_size,
            random_state=args.random_state,
        ),
    )
    artifact = save_artifact(result, settings.MODEL_DIR)
    print(f"Problem type: {result.problem_type}  estimator: {result.metadata['estimator']}")
    print(f"Rows: {json.dumps(result.metadata['rows'])}")
    for split in ("validation", "test", "baseline_test"):
        scalar = {k: v for k, v in result.metrics[split].items() if not isinstance(v, dict)}
        print(f"{split:>13}: {json.dumps(scalar)}")
    print(f"Artifact: {artifact.path}  sha256={artifact.sha256}")


if __name__ == "__main__":
    main()
