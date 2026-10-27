"""Write the seeded synthetic demo datasets to datasets/examples/.

Usage: python scripts/generate_synthetic_data.py [--rows 300] [--seed 42]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ml.synthetic import make_classification_frame, make_regression_frame  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "datasets" / "examples")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for name, frame in {
        "synthetic_classification.csv": make_classification_frame(args.rows, args.seed),
        "synthetic_regression.csv": make_regression_frame(args.rows, args.seed),
    }.items():
        path = args.out / name
        frame.to_csv(path, index=False)
        print(f"Wrote {path} ({len(frame)} rows, {frame.shape[1]} columns)")


if __name__ == "__main__":
    main()
