"""Validate and profile a local CSV/XLSX file; write summary JSON and PNG charts.

Usage: python scripts/profile_dataset.py datasets/examples/synthetic_classification.csv \
           [--target label] [--out reports/profile]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import load_settings  # noqa: E402
from app.ml.ingestion import detect_file_format, read_tabular_file  # noqa: E402
from app.ml.profiling import summarize_dataframe  # noqa: E402
from app.ml.validation import validate_dataframe  # noqa: E402
from app.ml.visualization import generate_report_figures  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--out", type=Path, default=ROOT / "reports" / "profile")
    args = parser.parse_args()

    settings = load_settings()
    frame = read_tabular_file(
        args.path,
        detect_file_format(args.path.name),
        max_rows=settings.MAX_DATASET_ROWS,
        max_columns=settings.MAX_DATASET_COLUMNS,
    )
    report = validate_dataframe(frame, target_column=args.target)
    args.out.mkdir(parents=True, exist_ok=True)
    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(
            {"validation": report.to_dict(), "summary": summarize_dataframe(frame)}, indent=2
        ),
        encoding="utf-8",
    )
    figures = generate_report_figures(frame, args.out)

    print(f"Rows x columns: {frame.shape[0]} x {frame.shape[1]}")
    print(f"Valid: {report.is_valid}  errors={len(report.errors)}  warnings={len(report.warnings)}")
    for issue in report.errors + report.warnings:
        print(f"  - [{issue.code}] {issue.column or ''} {issue.message}")
    print(f"Wrote {summary_path} and {len(figures)} figure(s) to {args.out}")
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
