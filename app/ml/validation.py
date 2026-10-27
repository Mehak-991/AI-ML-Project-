"""Dataset schema validation producing a structured report of errors and warnings."""

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from app.ml.profiling import ColumnKind, infer_column_kind

HIGH_MISSING_RATIO = 0.5


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    column: str | None = None


@dataclass
class ValidationReport:
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def error(self, code: str, message: str, column: str | None = None) -> None:
        self.errors.append(ValidationIssue(code, message, column))

    def warn(self, code: str, message: str, column: str | None = None) -> None:
        self.warnings.append(ValidationIssue(code, message, column))

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [asdict(issue) for issue in self.errors],
            "warnings": [asdict(issue) for issue in self.warnings],
        }


def validate_dataframe(
    df: pd.DataFrame,
    *,
    target_column: str | None = None,
    required_columns: list[str] | None = None,
    expected_kinds: dict[str, ColumnKind] | None = None,
    min_rows: int = 1,
) -> ValidationReport:
    report = ValidationReport()

    if df.shape[1] == 0 or df.empty:
        report.error("empty_dataset", "The dataset has no rows or no columns.")
        return report
    if len(df) < min_rows:
        report.error("too_few_rows", f"At least {min_rows} rows are required; found {len(df)}.")

    for column in df.columns:
        name = str(column)
        if not name or name.startswith("Unnamed:"):
            report.error("unnamed_column", "Every column needs a header name.", name)

    for column in required_columns or []:
        if column not in df.columns:
            report.error("missing_column", f"Required column '{column}' is missing.", column)

    for column, expected in (expected_kinds or {}).items():
        if column in df.columns and (actual := infer_column_kind(df[column])) != expected:
            report.error(
                "type_mismatch", f"Expected {expected} values but found {actual}.", column
            )

    for column in df.columns:
        series = df[column]
        missing_ratio = float(series.isna().mean())
        if missing_ratio == 1.0:
            report.warn("all_missing", "Column has no values.", str(column))
            continue
        if missing_ratio > HIGH_MISSING_RATIO:
            report.warn("high_missing", f"{missing_ratio:.0%} of values are missing.", str(column))
        if series.nunique(dropna=True) == 1:
            report.warn("constant_column", "Column has a single distinct value.", str(column))

    duplicate_count = int(df.duplicated().sum())
    if duplicate_count:
        report.warn("duplicate_rows", f"{duplicate_count} exact duplicate rows found.")

    if target_column is not None:
        if target_column not in df.columns:
            report.error(
                "missing_target", f"Target column '{target_column}' not found.", target_column
            )
        else:
            target = df[target_column]
            missing = int(target.isna().sum())
            if missing:
                report.warn(
                    "target_missing_values",
                    f"{missing} rows have no target value and will be dropped for training.",
                    target_column,
                )
            if target.nunique(dropna=True) < 2:
                report.error(
                    "degenerate_target",
                    "The target needs at least two distinct values.",
                    target_column,
                )
            if df.shape[1] < 2:
                report.error("no_features", "No feature columns besides the target.")
    return report
