import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import DataValidationError, ModelArtifactError, TrainingError
from app.ml import persistence
from app.ml.prediction import predict, validate_records
from app.ml.synthetic import make_classification_frame, make_regression_frame
from app.ml.training import TrainingConfig, infer_problem_type, train_model

CLASSIFICATION_METRICS = {
    "accuracy",
    "balanced_accuracy",
    "precision_macro",
    "recall_macro",
    "f1_macro",
    "confusion_matrix",
    "log_loss",
    "roc_auc",
}
REGRESSION_METRICS = {"mae", "rmse", "median_absolute_error", "r2"}


@pytest.fixture(scope="module")
def classification_result():
    return train_model(make_classification_frame(300, seed=1), TrainingConfig(target_column="label"))


@pytest.fixture(scope="module")
def regression_result():
    return train_model(make_regression_frame(300, seed=1), TrainingConfig(target_column="value"))


# --- problem type ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["a", "b"], "classification"),
        ([True, False], "classification"),
        ([0, 1, 2, 1], "classification"),
        ([0.0, 1.0, 1.0], "classification"),
        ([0.5, 1.7, 2.2], "regression"),
        (list(range(100)), "regression"),
    ],
)
def test_infer_problem_type(values, expected: str) -> None:
    assert infer_problem_type(pd.Series(values)) == expected


# --- training and evaluation -------------------------------------------------------


def test_classification_training(classification_result) -> None:
    result = classification_result
    assert result.problem_type == "classification"
    assert result.class_labels == ["no", "yes"]
    assert CLASSIFICATION_METRICS <= set(result.metrics["test"])
    assert set(result.metrics) == {"train", "validation", "test", "baseline_test"}
    # The signal is real, so the model must beat the majority-class baseline.
    assert result.metrics["test"]["accuracy"] > result.metrics["baseline_test"]["accuracy"]
    assert result.metadata["rows"]["dropped_duplicates"] == 5
    assert result.metadata["stratified"] is True
    assert "label" not in [f.name for f in result.features]


def test_regression_training(regression_result) -> None:
    result = regression_result
    assert result.problem_type == "regression"
    assert result.class_labels is None
    assert REGRESSION_METRICS <= set(result.metrics["test"])
    assert "accuracy" not in result.metrics["test"]
    assert result.metrics["test"]["r2"] > 0.8
    assert result.metrics["test"]["rmse"] < result.metrics["baseline_test"]["rmse"]


def test_random_forest_and_explicit_problem_type() -> None:
    result = train_model(
        make_classification_frame(150, seed=3),
        TrainingConfig(target_column="label", algorithm="random_forest", problem_type="classification"),
    )
    assert result.metadata["estimator"] == "RandomForestClassifier"
    assert result.metadata["config"]["problem_type_inferred"] is False


def test_multiclass_metrics() -> None:
    df = make_regression_frame(300, seed=2)
    df["band"] = pd.cut(df["value"], 3, labels=["low", "mid", "high"]).astype(str)
    result = train_model(df.drop(columns="value"), TrainingConfig(target_column="band"))
    assert len(result.class_labels) == 3
    assert "roc_auc_ovr_macro" in result.metrics["test"]


def test_preprocessing_is_fitted_on_training_split_only(classification_result) -> None:
    """Imputer medians must come from the training rows, not the full dataset (no leakage)."""
    result = classification_result
    df = make_classification_frame(300, seed=1).drop_duplicates()
    numeric = result.pipeline.named_steps["preprocess"].named_transformers_["numeric"]
    fitted_median = numeric.named_steps["impute"].statistics_[0]
    full_median = df["num_a"].median()
    assert result.metadata["rows"]["train"] < len(df)
    assert fitted_median != pytest.approx(full_median, abs=1e-9)


def test_rows_with_missing_target_are_dropped() -> None:
    df = make_classification_frame(100, seed=4, n_duplicates=0)
    df.loc[:9, "label"] = None
    result = train_model(df, TrainingConfig(target_column="label"))
    assert result.metadata["rows"]["dropped_missing_target"] == 10


@pytest.mark.parametrize(
    ("mutate", "config", "message"),
    [
        (lambda d: d.head(10), {}, "At least"),
        (lambda d: d.assign(label="same"), {}, "two distinct"),
        (lambda d: d, {"target_column": "nope"}, "not found"),
        (lambda d: d, {"problem_type": "regression"}, "numeric target"),
        (lambda d: d.assign(label=np.linspace(0, 1, len(d))), {"problem_type": "classification"}, "labels"),
        (lambda d: d[["label"]], {}, "No usable feature"),
        (lambda d: d, {"feature_columns": ["ghost"]}, "Unknown feature"),
    ],
)
def test_training_errors(mutate, config, message: str) -> None:
    df = mutate(make_classification_frame(100, seed=5, n_duplicates=0))
    with pytest.raises(TrainingError, match=message):
        train_model(df, TrainingConfig(**({"target_column": "label"} | config)))


# --- persistence -------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path, classification_result) -> None:
    artifact = persistence.save_artifact(classification_result, tmp_path)
    assert artifact.path.parent == tmp_path.resolve()
    payload = persistence.load_artifact(tmp_path, artifact.filename, artifact.sha256)
    assert payload["feature_schema"] == classification_result.feature_schema
    sample = make_classification_frame(20, seed=9, n_duplicates=0)
    features = validate_records(
        sample.drop(columns="label").to_dict("records"),
        classification_result.feature_schema,
        allow_missing=True,
    )
    original, _ = predict(classification_result.pipeline, features, "classification")
    reloaded, _ = predict(payload["pipeline"], features, "classification")
    assert original == reloaded


def test_tampered_artifact_is_rejected(tmp_path, classification_result) -> None:
    artifact = persistence.save_artifact(classification_result, tmp_path)
    with artifact.path.open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ModelArtifactError, match="integrity"):
        persistence.load_artifact(tmp_path, artifact.filename, artifact.sha256)


@pytest.mark.parametrize("filename", ["../x.joblib", "model.pkl", "a" * 32 + ".joblib"])
def test_load_artifact_rejects_bad_references(tmp_path, filename: str) -> None:
    with pytest.raises(ModelArtifactError):
        persistence.load_artifact(tmp_path, filename, "0" * 64)


# --- prediction validation ---------------------------------------------------------

SCHEMA = [{"name": "n", "kind": "numeric"}, {"name": "c", "kind": "categorical"}]


def test_validate_records_accepts_good_input() -> None:
    frame = validate_records([{"n": 1, "c": "a"}, {"n": 2.5, "c": 3}], SCHEMA)
    assert frame["n"].tolist() == [1.0, 2.5]
    assert frame["c"].tolist() == ["a", "3"]


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ({"n": 1}, "Feature is required."),
        ({"n": 1, "c": "a", "x": 1}, "Unknown feature."),
        ({"n": "1", "c": "a"}, "Expected a number."),
        ({"n": True, "c": "a"}, "Expected a number."),
        ({"n": float("nan"), "c": "a"}, "Expected a finite number."),
        ({"n": None, "c": "a"}, "Missing value"),
        ({"n": 1, "c": ""}, "Empty string"),
        ({"n": 1, "c": ["a"]}, "Expected a string"),
    ],
)
def test_validate_records_rejects_bad_input(record, message: str) -> None:
    with pytest.raises(DataValidationError) as exc_info:
        validate_records([record], SCHEMA)
    assert any(message in d["message"] for d in exc_info.value.details)
    assert exc_info.value.details[0]["record"] == 0


def test_validate_records_allow_missing() -> None:
    frame = validate_records([{"n": None, "c": ""}], SCHEMA, allow_missing=True)
    assert frame.isna().all(axis=None)


def test_validate_records_limits() -> None:
    with pytest.raises(DataValidationError, match="At least one"):
        validate_records([], SCHEMA)
    with pytest.raises(DataValidationError, match="At most 2"):
        validate_records([{"n": 1, "c": "a"}] * 3, SCHEMA, max_records=2)


def test_predict_outputs(classification_result, regression_result) -> None:
    sample = make_classification_frame(5, seed=11, n_duplicates=0).drop(columns="label")
    features = validate_records(
        sample.to_dict("records"), classification_result.feature_schema, allow_missing=True
    )
    predictions, probabilities = predict(classification_result.pipeline, features, "classification")
    assert set(predictions) <= {"yes", "no"}
    assert all(sum(p.values()) == pytest.approx(1.0) for p in probabilities)

    sample = make_regression_frame(5, seed=11, n_duplicates=0).drop(columns="value")
    features = validate_records(
        sample.to_dict("records"), regression_result.feature_schema, allow_missing=True
    )
    predictions, probabilities = predict(regression_result.pipeline, features, "regression")
    assert probabilities is None
    assert all(isinstance(p, float) for p in predictions)
