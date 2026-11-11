"""Validating prediction inputs against a model's feature schema and predicting."""

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from app.core.exceptions import DataValidationError
from app.ml.preprocessing import FeatureSpec, coerce_features
from app.ml.utils import round_or_none, to_python

MAX_REPORTED_ERRORS = 50


def _check_value(value: Any, kind: str, allow_missing: bool) -> str | None:
    """Return an error message, or None if the value is acceptable."""
    # NaN cannot arrive via JSON, but does when Python callers pass pandas records.
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None if allow_missing else "Missing value (null) is not allowed."
    if kind == "numeric":
        if isinstance(value, bool) or not isinstance(value, int | float):
            return "Expected a number."
        if not math.isfinite(value):
            return "Expected a finite number."
        return None
    if not isinstance(value, str | int | float | bool):
        return "Expected a string, number or boolean category."
    if isinstance(value, str) and not value.strip():
        return None if allow_missing else "Empty string is treated as missing and is not allowed."
    return None


def validate_records(
    records: list[dict[str, Any]],
    feature_schema: list[dict[str, str]],
    *,
    allow_missing: bool = False,
    max_records: int = 1000,
) -> pd.DataFrame:
    """Check names, types and missing values; return a typed feature DataFrame."""
    if not records:
        raise DataValidationError("At least one record is required.")
    if len(records) > max_records:
        raise DataValidationError(f"At most {max_records} records per request.")

    specs = [FeatureSpec(f["name"], f["kind"]) for f in feature_schema]  # type: ignore[arg-type]
    expected = {spec.name: spec.kind for spec in specs}
    errors: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        for name in sorted(set(record) - set(expected)):
            errors.append({"record": index, "field": name, "message": "Unknown feature."})
        for name, kind in expected.items():
            if name not in record:
                errors.append({"record": index, "field": name, "message": "Feature is required."})
                continue
            if message := _check_value(record[name], kind, allow_missing):
                errors.append({"record": index, "field": name, "message": message})
        if len(errors) >= MAX_REPORTED_ERRORS:
            break
    if errors:
        raise DataValidationError(
            "Prediction input failed validation.", details=errors[:MAX_REPORTED_ERRORS]
        )

    frame = pd.DataFrame.from_records(records, columns=list(expected))
    frame = frame.map(
        lambda v: np.nan if v is None or (isinstance(v, str) and not v.strip()) else v
    )
    return coerce_features(frame, specs)


def predict(
    pipeline: Pipeline, features: pd.DataFrame, problem_type: str
) -> tuple[list[Any], list[dict[str, float]] | None]:
    predictions = [to_python(value) for value in pipeline.predict(features)]
    if problem_type == "regression":
        return [round_or_none(value) for value in predictions], None
    if not hasattr(pipeline, "predict_proba"):
        return predictions, None
    labels = [str(to_python(label)) for label in pipeline.classes_]
    probabilities = [
        {label: round(float(p), 6) for label, p in zip(labels, row, strict=True)}
        for row in pipeline.predict_proba(features)
    ]
    return predictions, probabilities
