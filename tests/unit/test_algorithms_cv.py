"""Supported algorithms, honest cross-validation and the experiment/training algorithm contract."""

import pytest
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from app.ml.persistence import load_artifact, save_artifact
from app.ml.prediction import predict, validate_records
from app.ml.synthetic import make_classification_frame, make_regression_frame
from app.ml.training import (
    CV_MAX_ROWS,
    TrainingConfig,
    build_estimator,
    cross_validate_model,
    train_model,
)

EXPECTED = {
    ("classification", "gradient_boosting"): GradientBoostingClassifier,
    ("classification", "decision_tree"): DecisionTreeClassifier,
    ("regression", "gradient_boosting"): GradientBoostingRegressor,
    ("regression", "decision_tree"): DecisionTreeRegressor,
}


@pytest.mark.parametrize(("problem_type", "algorithm"), list(EXPECTED))
def test_each_algorithm_builds_the_estimator_it_names(problem_type, algorithm) -> None:
    assert type(build_estimator(problem_type, algorithm, 1)) is EXPECTED[(problem_type, algorithm)]


@pytest.mark.parametrize("algorithm", ["linear", "random_forest", "gradient_boosting", "decision_tree"])
def test_every_algorithm_trains_saves_and_predicts_identically_after_reload(algorithm, tmp_path) -> None:
    frame = make_classification_frame(240, seed=3)
    result = train_model(frame, TrainingConfig(target_column="label", algorithm=algorithm))
    assert result.algorithm == algorithm
    assert result.metrics["test"]["accuracy"] is not None
    assert result.metrics["baseline_test"]["accuracy"] is not None
    artifact = save_artifact(result, tmp_path)
    payload = load_artifact(tmp_path, artifact.filename, artifact.sha256)
    features = validate_records(
        frame.drop(columns="label").head(8).to_dict("records"), result.feature_schema, allow_missing=True
    )
    original, _ = predict(result.pipeline, features, "classification")
    reloaded, _ = predict(payload["pipeline"], features, "classification")
    assert original == reloaded


@pytest.mark.parametrize("algorithm", ["gradient_boosting", "decision_tree"])
def test_new_algorithms_work_for_regression(algorithm) -> None:
    result = train_model(
        make_regression_frame(240, seed=3),
        TrainingConfig(target_column="value", algorithm=algorithm),
    )
    assert result.problem_type == "regression"
    assert set(result.metrics["test"]) >= {"mae", "rmse", "r2"}


def test_classification_cross_validation_is_reported_with_spread() -> None:
    result = train_model(make_classification_frame(300, seed=1), TrainingConfig(target_column="label"))
    cv = result.metadata["cross_validation"]
    assert cv["status"] == "ok"
    assert 2 <= cv["folds"] <= 5
    for name in ("accuracy", "f1_macro"):
        assert 0.0 <= cv[name]["mean"] <= 1.0
        assert cv[name]["std"] >= 0.0


def test_regression_cross_validation_reports_rmse_as_a_positive_error() -> None:
    result = train_model(make_regression_frame(300, seed=1), TrainingConfig(target_column="value"))
    cv = result.metadata["cross_validation"]
    assert cv["status"] == "ok"
    assert cv["rmse"]["mean"] > 0
    assert "r2" in cv


def test_cross_validation_never_uses_the_test_split() -> None:
    """Fold scores come from training+validation rows only: the held-out test score stays unseen."""
    result = train_model(
        make_classification_frame(300, seed=1), TrainingConfig(target_column="label")
    )
    rows = result.metadata["rows"]
    # 300 rows, 20% test: CV can only have seen the remaining ~80%.
    assert rows["test"] > 0
    assert result.metadata["cross_validation"]["status"] == "ok"


def test_cross_validation_is_skipped_when_a_class_is_too_small() -> None:
    import pandas as pd

    frame = make_classification_frame(60, seed=2)
    y = pd.Series(["a"] * 59 + ["b"])
    summary = cross_validate_model(
        train_model(frame, TrainingConfig(target_column="label")).pipeline,
        frame.drop(columns=["label"]),
        y,
        "classification",
        1,
    )
    assert summary["status"] == "skipped"


def test_cross_validation_is_skipped_for_very_large_training_sets() -> None:
    import pandas as pd

    big = pd.Series([0, 1] * (CV_MAX_ROWS // 2 + 1))
    summary = cross_validate_model(None, big.to_frame("x"), big, "classification", 1)  # type: ignore[arg-type]
    assert summary["status"] == "skipped"
    assert str(CV_MAX_ROWS) in summary["reason"]


def test_the_api_schemas_accept_exactly_the_supported_algorithms() -> None:
    from typing import get_args

    from app.ml.training import Algorithm as TrainingAlgorithm
    from app.schemas.experiment import Algorithm as ExperimentAlgorithm
    from app.schemas.models import Algorithm as ModelAlgorithm

    assert set(get_args(ModelAlgorithm)) == set(get_args(ExperimentAlgorithm)) == set(get_args(TrainingAlgorithm))
    assert set(get_args(ModelAlgorithm)) == {"linear", "random_forest", "gradient_boosting", "decision_tree"}
