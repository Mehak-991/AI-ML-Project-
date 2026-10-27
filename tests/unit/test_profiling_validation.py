import json

import numpy as np
import pandas as pd

from app.ml.profiling import (
    column_schema,
    duplicate_report,
    infer_column_kind,
    missing_value_report,
    summarize_dataframe,
)
from app.ml.validation import validate_dataframe


def test_missing_value_report() -> None:
    df = pd.DataFrame({"a": [1, None, 3, None], "b": ["x", "y", None, "z"], "c": [1, 2, 3, 4]})
    report = missing_value_report(df)
    assert report["total_missing_cells"] == 3
    assert report["rows_with_missing"] == 3
    assert report["columns"][0] == {"column": "a", "missing_count": 2, "missing_ratio": 0.5}
    assert {c["column"] for c in report["columns"]} == {"a", "b"}


def test_duplicate_report() -> None:
    df = pd.DataFrame({"a": [1, 1, 2, 1], "b": ["x", "x", "y", "x"]})
    report = duplicate_report(df)
    assert report["duplicate_rows"] == 2
    assert report["sample_row_indices"] == [1, 3]
    assert duplicate_report(df, subset=["b"])["duplicate_rows"] == 2


def test_infer_column_kind() -> None:
    assert infer_column_kind(pd.Series([1.0, 2.5])) == "numeric"
    assert infer_column_kind(pd.Series([True, False])) == "boolean"
    assert infer_column_kind(pd.Series(["a", "b", "a"])) == "categorical"
    assert infer_column_kind(pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01"]))) == "datetime"
    assert infer_column_kind(pd.Series([f"id-{i}" for i in range(100)])) == "text"


def test_summary_is_json_serializable(classification_df) -> None:
    df = classification_df.copy()
    df["inf"] = np.inf
    df["when"] = pd.Timestamp("2024-01-01")
    summary = summarize_dataframe(df)
    json.dumps(summary)  # must not raise on NaN/inf/NumPy types
    assert summary["n_rows"] == len(df)
    by_name = {c["name"]: c for c in summary["columns"]}
    assert by_name["num_a"]["kind"] == "numeric"
    assert set(by_name["num_a"]["stats"]) >= {"mean", "std", "min", "max"}
    assert by_name["cat_a"]["top_values"]
    assert summary["duplicates"]["duplicate_rows"] >= 1


def test_column_schema(classification_df) -> None:
    schema = column_schema(classification_df)
    assert {"name": "cat_a", "dtype": "object", "kind": "categorical"} in schema


def test_validation_of_clean_data(classification_df) -> None:
    report = validate_dataframe(classification_df.drop_duplicates(), target_column="label")
    assert report.is_valid
    assert all(w.code != "duplicate_rows" for w in report.warnings)


def test_validation_errors_and_warnings() -> None:
    df = pd.DataFrame(
        {
            "Unnamed: 0": [0, 1, 2],
            "empty": [None, None, None],
            "const": [1, 1, 1],
            "mostly_missing": [1, None, None],
            "kind": ["a", "b", "c"],
            "target": ["y", "y", "y"],
        }
    )
    report = validate_dataframe(
        df,
        target_column="target",
        required_columns=["missing_col"],
        expected_kinds={"kind": "numeric"},
        min_rows=5,
    )
    error_codes = {e.code for e in report.errors}
    warning_codes = {w.code for w in report.warnings}
    assert {
        "too_few_rows",
        "unnamed_column",
        "missing_column",
        "type_mismatch",
        "degenerate_target",
    } <= error_codes
    assert {"all_missing", "constant_column", "high_missing"} <= warning_codes
    assert not report.is_valid
    json.dumps(report.to_dict())


def test_validation_missing_target_and_target_nulls() -> None:
    df = pd.DataFrame({"x": [1, 2, 3], "y": [1, None, 0]})
    assert validate_dataframe(df, target_column="nope").errors[0].code == "missing_target"
    report = validate_dataframe(df, target_column="y")
    assert report.is_valid
    assert any(w.code == "target_missing_values" for w in report.warnings)


def test_validation_empty_dataset() -> None:
    assert validate_dataframe(pd.DataFrame()).errors[0].code == "empty_dataset"
