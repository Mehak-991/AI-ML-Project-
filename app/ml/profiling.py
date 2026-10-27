"""Column typing, missing-value and duplicate analysis, dataset summaries."""

from typing import Any, Literal

import numpy as np
import pandas as pd

from app.ml.utils import round_or_none, to_python

ColumnKind = Literal["numeric", "categorical", "boolean", "datetime", "text"]

# Object columns with this many distinct values, mostly unique, are treated as free text / IDs.
TEXT_MIN_UNIQUE = 50
TEXT_UNIQUE_RATIO = 0.5


def infer_column_kind(series: pd.Series) -> ColumnKind:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    non_null = series.dropna()
    n_unique = non_null.nunique()
    if n_unique >= TEXT_MIN_UNIQUE and n_unique / max(len(non_null), 1) > TEXT_UNIQUE_RATIO:
        return "text"
    return "categorical"


def missing_value_report(df: pd.DataFrame) -> dict[str, Any]:
    counts = df.isna().sum()
    n_rows = max(len(df), 1)
    columns = [
        {
            "column": str(column),
            "missing_count": int(count),
            "missing_ratio": round(int(count) / n_rows, 6),
        }
        for column, count in counts.sort_values(ascending=False).items()
        if count > 0
    ]
    return {
        "total_missing_cells": int(counts.sum()),
        "rows_with_missing": int(df.isna().any(axis=1).sum()),
        "columns": columns,
    }


def duplicate_report(
    df: pd.DataFrame, subset: list[str] | None = None, sample_size: int = 10
) -> dict[str, Any]:
    """Exact duplicate rows (all columns, or `subset`). The first occurrence is not counted."""
    mask = df.duplicated(subset=subset, keep="first")
    count = int(mask.sum())
    return {
        "duplicate_rows": count,
        "duplicate_ratio": round(count / max(len(df), 1), 6),
        "sample_row_indices": [int(i) for i in df.index[mask][:sample_size]],
    }


def summarize_column(series: pd.Series, top_k: int = 5) -> dict[str, Any]:
    kind = infer_column_kind(series)
    non_null = series.dropna()
    summary: dict[str, Any] = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "kind": kind,
        "missing_count": int(series.isna().sum()),
        "missing_ratio": round(float(series.isna().mean()), 6) if len(series) else 0.0,
        "unique_count": int(non_null.nunique()),
    }
    if kind == "numeric" and not non_null.empty:
        infinite = np.isinf(non_null.to_numpy(dtype=float))
        summary["infinite_count"] = int(infinite.sum())
        finite = non_null[~infinite]
        described = finite.describe() if not finite.empty else pd.Series(dtype=float)
        summary["stats"] = {
            key: round_or_none(described.get(key))
            for key in ("mean", "std", "min", "25%", "50%", "75%", "max")
        }
    elif kind in ("categorical", "boolean", "text") and not non_null.empty:
        counts = non_null.astype(str).value_counts().head(top_k)
        summary["top_values"] = [
            {"value": str(value), "count": int(count)} for value, count in counts.items()
        ]
    elif kind == "datetime" and not non_null.empty:
        summary["stats"] = {"min": to_python(non_null.min()), "max": to_python(non_null.max())}
    return summary


def summarize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "n_rows": len(df),
        "n_columns": int(df.shape[1]),
        "memory_bytes": int(df.memory_usage(deep=True).sum()),
        "columns": [summarize_column(df[column]) for column in df.columns],
        "missing_values": missing_value_report(df),
        "duplicates": duplicate_report(df),
    }


def column_schema(df: pd.DataFrame) -> list[dict[str, str]]:
    """Lightweight per-column schema stored with each dataset record."""
    return [
        {"name": str(column), "dtype": str(df[column].dtype), "kind": infer_column_kind(df[column])}
        for column in df.columns
    ]
