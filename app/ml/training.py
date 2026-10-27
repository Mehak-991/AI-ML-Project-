"""Baseline training pipeline: clean -> split -> fit (train only) -> evaluate.

Leakage controls:
- the target and any excluded columns are never features;
- exact duplicate rows are dropped *before* splitting so copies cannot land in
  both train and test;
- all imputation, scaling and encoding live inside the sklearn Pipeline and are
  fitted on the training split only;
- the test split is used once, for final reporting.
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import BaseEstimator
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline

from app.core.exceptions import TrainingError
from app.ml.preprocessing import (
    DataSplits,
    FeatureSpec,
    build_preprocessor,
    coerce_features,
    drop_duplicate_rows,
    select_features,
    split_dataset,
)
from app.ml.utils import round_or_none, to_python

ProblemType = Literal["classification", "regression"]
Algorithm = Literal["linear", "random_forest"]

MIN_TRAINING_ROWS = 20
# Integer targets with at most this many distinct values are treated as class labels.
MAX_CLASSES_FOR_INTEGER_TARGET = 20


@dataclass
class TrainingConfig:
    target_column: str
    problem_type: ProblemType | None = None  # None = infer from the target
    algorithm: Algorithm = "linear"
    feature_columns: list[str] | None = None
    exclude_columns: list[str] = field(default_factory=list)
    test_size: float = 0.2
    validation_size: float = 0.2
    random_state: int = 42
    drop_duplicates: bool = True


@dataclass
class TrainingResult:
    pipeline: Pipeline
    problem_type: ProblemType
    algorithm: Algorithm
    target_column: str
    features: list[FeatureSpec]
    class_labels: list[Any] | None
    metrics: dict[str, dict[str, Any]]
    metadata: dict[str, Any]

    @property
    def feature_schema(self) -> list[dict[str, str]]:
        return [spec.to_dict() for spec in self.features]


def infer_problem_type(target: pd.Series) -> ProblemType:
    values = target.dropna()
    if not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
        return "classification"
    is_integer_valued = bool(np.all(np.mod(values.to_numpy(dtype=float), 1) == 0))
    if is_integer_valued and values.nunique() <= MAX_CLASSES_FOR_INTEGER_TARGET:
        return "classification"
    return "regression"


def build_estimator(problem_type: ProblemType, algorithm: Algorithm, random_state: int):
    if problem_type == "classification":
        if algorithm == "random_forest":
            return RandomForestClassifier(n_estimators=200, random_state=random_state)
        return LogisticRegression(max_iter=2000)
    if algorithm == "random_forest":
        return RandomForestRegressor(n_estimators=200, random_state=random_state)
    return Ridge(alpha=1.0)


def classification_metrics(
    model: BaseEstimator, X: pd.DataFrame, y: pd.Series
) -> dict[str, Any]:
    if len(y) == 0:
        return {}
    predicted = model.predict(X)
    metrics: dict[str, Any] = {
        "n_samples": len(y),
        "accuracy": round_or_none(accuracy_score(y, predicted)),
        "balanced_accuracy": round_or_none(balanced_accuracy_score(y, predicted)),
        "precision_macro": round_or_none(
            precision_score(y, predicted, average="macro", zero_division=0)
        ),
        "recall_macro": round_or_none(recall_score(y, predicted, average="macro", zero_division=0)),
        "f1_macro": round_or_none(f1_score(y, predicted, average="macro", zero_division=0)),
    }
    labels = list(model.classes_)
    metrics["confusion_matrix"] = {
        "labels": [to_python(label) for label in labels],
        "matrix": confusion_matrix(y, predicted, labels=labels).tolist(),
    }
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(X)
        metrics["log_loss"] = round_or_none(log_loss(y, probabilities, labels=labels))
        try:
            if len(labels) == 2:
                metrics["roc_auc"] = round_or_none(roc_auc_score(y, probabilities[:, 1]))
            else:
                metrics["roc_auc_ovr_macro"] = round_or_none(
                    roc_auc_score(y, probabilities, multi_class="ovr", labels=labels)
                )
        except ValueError:
            pass  # A class is absent from this split; AUC is undefined.
    return metrics


def regression_metrics(model: BaseEstimator, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
    if len(y) == 0:
        return {}
    predicted = model.predict(X)
    return {
        "n_samples": len(y),
        "mae": round_or_none(mean_absolute_error(y, predicted)),
        "rmse": round_or_none(float(np.sqrt(mean_squared_error(y, predicted)))),
        "median_absolute_error": round_or_none(median_absolute_error(y, predicted)),
        "r2": round_or_none(r2_score(y, predicted)) if len(y) > 1 else None,
    }


def _prepare_target(target: pd.Series, problem_type: ProblemType) -> pd.Series:
    if problem_type == "regression":
        if not pd.api.types.is_numeric_dtype(target) or pd.api.types.is_bool_dtype(target):
            raise TrainingError("Regression needs a numeric target column.")
        return target.astype(float)
    if pd.api.types.is_numeric_dtype(target) and not pd.api.types.is_bool_dtype(target):
        as_float = target.astype(float)
        if np.all(np.mod(as_float, 1) == 0):
            return as_float.astype(int)
        raise TrainingError("Classification targets must be labels, not continuous numbers.")
    if pd.api.types.is_bool_dtype(target):
        return target
    return target.astype(str)


def train_model(df: pd.DataFrame, config: TrainingConfig) -> TrainingResult:
    started = time.perf_counter()
    if config.target_column not in df.columns:
        raise TrainingError(f"Target column '{config.target_column}' not found.")
    n_rows_raw = len(df)

    data = df.dropna(subset=[config.target_column])
    dropped_missing_target = n_rows_raw - len(data)

    try:
        features, dropped_columns = select_features(
            data,
            config.target_column,
            include=config.feature_columns,
            exclude=config.exclude_columns,
        )
    except ValueError as exc:
        raise TrainingError(str(exc)) from None
    if not features:
        raise TrainingError("No usable feature columns remain after filtering.")

    # Deduplicate on the modelling columns only, before any split.
    data = data[[f.name for f in features] + [config.target_column]]
    dropped_duplicates = 0
    if config.drop_duplicates:
        data, dropped_duplicates = drop_duplicate_rows(data)
    if len(data) < MIN_TRAINING_ROWS:
        raise TrainingError(
            f"At least {MIN_TRAINING_ROWS} usable rows are required; {len(data)} remain."
        )

    problem_type = config.problem_type or infer_problem_type(data[config.target_column])
    y = _prepare_target(data[config.target_column], problem_type)
    if y.nunique() < 2:
        raise TrainingError("The target needs at least two distinct values.")
    X = coerce_features(data, features)

    try:
        splits: DataSplits = split_dataset(
            X,
            y,
            test_size=config.test_size,
            validation_size=config.validation_size,
            random_state=config.random_state,
            stratify=problem_type == "classification",
        )
    except ValueError as exc:
        raise TrainingError(str(exc)) from None
    if problem_type == "classification" and splits.y_train.nunique() < 2:
        raise TrainingError("The training split contains only one class.")

    pipeline = Pipeline(
        [
            ("preprocess", build_preprocessor(features)),
            ("model", build_estimator(problem_type, config.algorithm, config.random_state)),
        ]
    )
    pipeline.fit(splits.X_train, splits.y_train)

    if problem_type == "classification":
        evaluate = classification_metrics
        baseline = DummyClassifier(strategy="most_frequent")
    else:
        evaluate = regression_metrics
        baseline = DummyRegressor(strategy="mean")
    baseline.fit(splits.X_train, splits.y_train)

    metrics = {
        "train": evaluate(pipeline, splits.X_train, splits.y_train),
        "validation": evaluate(pipeline, splits.X_val, splits.y_val),
        "test": evaluate(pipeline, splits.X_test, splits.y_test),
        "baseline_test": evaluate(baseline, splits.X_test, splits.y_test),
    }
    class_labels = (
        [to_python(label) for label in pipeline.classes_]
        if problem_type == "classification"
        else None
    )
    metadata = {
        "trained_at": datetime.now(UTC).isoformat(),
        "training_seconds": round(time.perf_counter() - started, 3),
        "rows": {
            "raw": n_rows_raw,
            "dropped_missing_target": dropped_missing_target,
            "dropped_duplicates": dropped_duplicates,
            "used": len(data),
            **splits.sizes(),
        },
        "stratified": splits.stratified,
        "dropped_columns": [{"column": d.column, "reason": d.reason} for d in dropped_columns],
        "config": {
            "test_size": config.test_size,
            "validation_size": config.validation_size,
            "random_state": config.random_state,
            "drop_duplicates": config.drop_duplicates,
            "problem_type_inferred": config.problem_type is None,
        },
        "baseline_model": type(baseline).__name__,
        "estimator": type(pipeline.named_steps["model"]).__name__,
        "versions": {
            "scikit-learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    return TrainingResult(
        pipeline=pipeline,
        problem_type=problem_type,
        algorithm=config.algorithm,
        target_column=config.target_column,
        features=features,
        class_labels=class_labels,
        metrics=metrics,
        metadata=metadata,
    )
