"""Automated ML pipeline and experiment tracking execution engine."""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sklearn
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    precision_score,
    r2_score,
    recall_score,
    root_mean_squared_error,
)
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, DataValidationError, NotFoundError
from app.database.models.experiment import Experiment, ExperimentRun
from app.database.models.ml_model import MLModel
from app.ml.persistence import delete_artifact, save_artifact
from app.ml.preprocessing import (
    build_preprocessor,
    coerce_features,
    drop_duplicate_rows,
    select_features,
    split_dataset,
)
from app.ml.training import MIN_TRAINING_ROWS, TrainingResult, _prepare_target, build_estimator
from app.ml.utils import to_python
from app.services.dataset_service import get_dataset, load_dataset_frame

logger = logging.getLogger(__name__)


def create_experiment(
    session: Session,
    dataset_id: uuid.UUID,
    name: str,
    target_column: str,
    problem_type: str,
    algorithm: str,
    user_id: uuid.UUID | None,
    description: str | None = None,
    selected_features: list[str] | None = None,
    hyperparameter_config: dict[str, Any] | None = None,
    search_strategy: str = "none",
    cv_folds: int = 5,
    scoring_metric: str | None = None,
    test_size: float = 0.2,
    validation_size: float = 0.1,
    random_state: int = 42,
) -> Experiment:
    dataset = get_dataset(session, dataset_id)

    experiment = Experiment(
        name=name,
        description=description,
        dataset_id=dataset.id,
        target_column=target_column,
        problem_type=problem_type,
        algorithm=algorithm,
        selected_features=selected_features,
        hyperparameter_config=hyperparameter_config or {},
        search_strategy=search_strategy,
        cv_folds=cv_folds,
        scoring_metric=scoring_metric,
        test_size=test_size,
        validation_size=validation_size,
        random_state=random_state,
        status="pending",
        dataset_fingerprint=dataset.sha256,
        created_by_id=user_id,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def get_experiment(session: Session, experiment_id: uuid.UUID) -> Experiment:
    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise NotFoundError(f"Experiment {experiment_id} not found")
    return experiment


def list_experiments(
    session: Session,
    offset: int = 0,
    limit: int = 20,
    status: str | None = None,
    owner_id: uuid.UUID | None = None,
) -> tuple[list[Experiment], int]:
    stmt = select(Experiment).order_by(desc(Experiment.created_at))
    if owner_id is not None:
        stmt = stmt.where(
            or_(Experiment.created_by_id == owner_id, Experiment.created_by_id.is_(None))
        )
    if status:
        stmt = stmt.where(Experiment.status == status)

    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = session.scalars(stmt.offset(offset).limit(limit)).all()
    return list(items), total


def _classification_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def _regression_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def _abandon_stale_runs(session: Session, experiment: Experiment, settings: Settings) -> None:
    """Refuse a concurrent run, but let a run orphaned by a crashed process be replaced."""
    if experiment.status != "running":
        return
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.JOB_STALE_TIMEOUT_MINUTES)
    active = [run for run in experiment.runs if run.status == "running"]
    # SQLite returns naive datetimes; PostgreSQL returns aware ones.
    started = [
        (run.started_at.replace(tzinfo=UTC) if run.started_at.tzinfo is None
         else run.started_at)
        for run in active
        if run.started_at is not None
    ]
    if any(value > cutoff for value in started):
        raise ConflictError("This experiment is already running.")
    for run in active:
        run.status = "failed"
        run.error_message = "Abandoned: the process running it stopped."
        run.completed_at = datetime.now(UTC)


def execute_pipeline_run(
    session: Session,
    settings: Settings,
    experiment_id: uuid.UUID,
) -> ExperimentRun:
    # The row lock makes "check not running, then mark running" atomic across processes.
    experiment = session.get(Experiment, experiment_id, with_for_update=True)
    if not experiment:
        raise NotFoundError(f"Experiment {experiment_id} not found")
    dataset = get_dataset(session, experiment.dataset_id)

    # Verify dataset reproducibility fingerprint
    if experiment.dataset_fingerprint and dataset.sha256 != experiment.dataset_fingerprint:
        raise DataValidationError(
            f"Dataset fingerprint mismatch: original={experiment.dataset_fingerprint}, current={dataset.sha256}"
        )
    _abandon_stale_runs(session, experiment, settings)

    # Create run entry
    run_count = len(experiment.runs)
    run = ExperimentRun(
        experiment_id=experiment.id,
        run_number=run_count + 1,
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    experiment.status = "running"
    experiment.completed_at = None
    if not experiment.started_at:
        experiment.started_at = run.started_at
    session.commit()
    session.refresh(run)
    run_id, exp_id = run.id, experiment.id

    start_time = time.perf_counter()
    saved_art = None

    try:
        # 1. Dataset loading. Same feature selection, de-duplication and type coercion as
        # model_service.train, so experiment models accept the same prediction input.
        df = load_dataset_frame(settings, dataset)
        target = experiment.target_column
        if target not in df.columns:
            raise DataValidationError(f"Target column '{target}' missing from dataset")
        df = df.dropna(subset=[target])

        # 2. Feature selection
        include = None
        if experiment.selected_features:
            include = [f for f in experiment.selected_features if f in df.columns and f != target]
            if not include:
                raise DataValidationError("No valid features selected for training")
        feature_specs, _ = select_features(df, target, include=include)
        if not feature_specs:
            raise DataValidationError("No valid features selected for training")

        # 3. De-duplicate before splitting so copies cannot land in both train and test
        data, _ = drop_duplicate_rows(df[[f.name for f in feature_specs] + [target]])
        if len(data) < MIN_TRAINING_ROWS:
            raise DataValidationError(
                f"At least {MIN_TRAINING_ROWS} usable rows are required; {len(data)} remain."
            )
        X = coerce_features(data, feature_specs)
        y = _prepare_target(data[target], experiment.problem_type)

        # 4. Train / Val / Test Split (Prevent Data Leakage)
        splits = split_dataset(
            X,
            y,
            test_size=experiment.test_size,
            validation_size=experiment.validation_size,
            random_state=experiment.random_state,
            stratify=experiment.problem_type == "classification",
        )

        # 5. Estimator Setup
        if experiment.algorithm in ("gradient_boosting", "decision_tree"):
            base_estimator = build_estimator(
                experiment.problem_type, experiment.algorithm, experiment.random_state
            )
        elif experiment.problem_type == "classification":
            base_estimator = (
                LogisticRegression(max_iter=2000, random_state=experiment.random_state)
                if experiment.algorithm == "linear"
                else RandomForestClassifier(random_state=experiment.random_state)
            )
        else:
            base_estimator = (
                Ridge(random_state=experiment.random_state)
                if experiment.algorithm == "linear"
                else RandomForestRegressor(random_state=experiment.random_state)
            )
        evaluate = (
            _classification_metrics
            if experiment.problem_type == "classification"
            else _regression_metrics
        )

        full_pipeline = Pipeline(
            steps=[
                ("preprocessor", build_preprocessor(feature_specs)),
                ("estimator", base_estimator),
            ]
        )

        # 6. Hyperparameter Optimization (Grid / Random Search)
        best_params: dict[str, Any] = {}
        cv_results: dict[str, Any] = {}

        if experiment.search_strategy in ("grid", "random") and experiment.hyperparameter_config:
            param_grid = {
                f"estimator__{k}": v for k, v in experiment.hyperparameter_config.items()
            }
            if experiment.search_strategy == "grid":
                search = GridSearchCV(
                    full_pipeline,
                    param_grid,
                    cv=experiment.cv_folds,
                    scoring=experiment.scoring_metric,
                    n_jobs=1,
                )
            else:
                search = RandomizedSearchCV(
                    full_pipeline,
                    param_grid,
                    n_iter=min(10, max(2, len(param_grid))),
                    cv=experiment.cv_folds,
                    scoring=experiment.scoring_metric,
                    random_state=experiment.random_state,
                    n_jobs=1,
                )

            search.fit(splits.X_train, splits.y_train)
            full_pipeline = search.best_estimator_
            best_params = {
                k.replace("estimator__", ""): v for k, v in search.best_params_.items()
            }
            cv_results = {"best_score": float(search.best_score_)}
        else:
            full_pipeline.fit(splits.X_train, splits.y_train)

        # 7. Evaluation on Validation & Test Sets
        val_metrics = (
            evaluate(splits.y_val, full_pipeline.predict(splits.X_val)) if len(splits.y_val) else {}
        )
        test_metrics = evaluate(splits.y_test, full_pipeline.predict(splits.X_test))

        # A cancel that arrived during training wins: register nothing.
        session.refresh(experiment)
        if experiment.status == "cancelled":
            session.refresh(run)
            return run

        # 8. Register in MLModel Registry
        duration = time.perf_counter() - start_time
        class_labels = (
            [to_python(label) for label in full_pipeline.classes_]
            if experiment.problem_type == "classification"
            else None
        )
        training_result = TrainingResult(
            pipeline=full_pipeline,
            problem_type=experiment.problem_type,
            algorithm=experiment.algorithm,
            target_column=target,
            features=feature_specs,
            class_labels=class_labels,
            metrics={"validation": val_metrics, "test": test_metrics},
            metadata={
                "trained_at": datetime.now(UTC).isoformat(),
                "training_seconds": round(duration, 4),
                "experiment_id": str(experiment.id),
                "run_id": str(run.id),
                "best_hyperparameters": best_params,
                "estimator": type(base_estimator).__name__,
                "class_labels": class_labels,
            },
        )
        saved_art = save_artifact(training_result, settings.MODEL_DIR)

        latest_ver = session.scalar(
            select(MLModel.version)
            .where(MLModel.name == experiment.name)
            .order_by(desc(MLModel.version))
            .limit(1)
        )
        version = (latest_ver or 0) + 1

        registered_model = MLModel(
            name=experiment.name,
            version=version,
            dataset_id=experiment.dataset_id,
            problem_type=experiment.problem_type,
            algorithm=experiment.algorithm,
            target_column=target,
            feature_schema=[s.to_dict() for s in feature_specs],
            metrics={"validation": val_metrics, "test": test_metrics},
            training_metadata=training_result.metadata,
            artifact_filename=saved_art.filename,
            artifact_sha256=saved_art.sha256,
            sklearn_version=sklearn.__version__,
            owner_id=experiment.created_by_id,
        )
        session.add(registered_model)
        session.flush()

        # Update Run details
        run.status = "completed"
        run.best_hyperparameters = best_params
        run.validation_metrics = val_metrics
        run.test_metrics = test_metrics
        run.cv_results = cv_results
        run.registered_model_id = registered_model.id
        run.completed_at = datetime.now(UTC)
        run.execution_duration_seconds = round(duration, 4)

        experiment.status = "completed"
        experiment.completed_at = run.completed_at
        experiment.execution_duration_seconds = run.execution_duration_seconds

        session.commit()
        session.refresh(run)
        return run

    except Exception as exc:
        # A failed flush leaves the transaction unusable; recording the failure needs a clean one.
        session.rollback()
        if saved_art is not None:
            delete_artifact(settings.MODEL_DIR, saved_art.filename)
        duration = time.perf_counter() - start_time
        run = session.get(ExperimentRun, run_id, populate_existing=True)
        experiment = session.get(Experiment, exp_id, populate_existing=True)
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(UTC)
        run.execution_duration_seconds = round(duration, 4)

        experiment.status = "failed"
        experiment.completed_at = run.completed_at
        experiment.execution_duration_seconds = run.execution_duration_seconds

        session.commit()
        session.refresh(run)
        logger.exception("Experiment run %s failed: %s", run.id, exc)
        return run


def cancel_experiment(session: Session, experiment_id: uuid.UUID) -> Experiment:
    experiment = get_experiment(session, experiment_id)
    if experiment.status not in ("pending", "running"):
        raise DataValidationError(f"Cannot cancel experiment in '{experiment.status}' status")

    experiment.status = "cancelled"
    experiment.completed_at = datetime.now(UTC)
    for run in experiment.runs:
        if run.status in ("pending", "running"):
            run.status = "cancelled"
            run.completed_at = experiment.completed_at

    session.commit()
    session.refresh(experiment)
    return experiment


def compare_experiments(session: Session, experiment_ids: list[uuid.UUID]) -> dict[str, Any]:
    if not experiment_ids:
        return {"experiments": [], "warnings": []}

    experiments = session.scalars(
        select(Experiment).where(Experiment.id.in_(experiment_ids))
    ).all()

    compare_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    dataset_ids = set()
    target_columns = set()

    for exp in experiments:
        dataset_ids.add(exp.dataset_id)
        target_columns.add(exp.target_column)

        latest_run = session.scalar(
            select(ExperimentRun)
            .where(ExperimentRun.experiment_id == exp.id)
            .order_by(desc(ExperimentRun.run_number))
            .limit(1)
        )

        compare_items.append(
            {
                "experiment_id": exp.id,
                "experiment_name": exp.name,
                "run_id": latest_run.id if latest_run else exp.id,
                "algorithm": exp.algorithm,
                "problem_type": exp.problem_type,
                "dataset_id": exp.dataset_id,
                "target_column": exp.target_column,
                "status": latest_run.status if latest_run else exp.status,
                "best_hyperparameters": latest_run.best_hyperparameters if latest_run else None,
                "validation_metrics": latest_run.validation_metrics if latest_run else None,
                "test_metrics": latest_run.test_metrics if latest_run else None,
                "execution_duration_seconds": latest_run.execution_duration_seconds if latest_run else exp.execution_duration_seconds,
                "created_at": exp.created_at,
            }
        )

    if len(dataset_ids) > 1:
        warnings.append("Comparing experiments trained on different datasets.")
    if len(target_columns) > 1:
        warnings.append("Comparing experiments predicting different target columns.")

    return {"experiments": compare_items, "warnings": warnings}
