"""Automated ML pipeline and experiment tracking execution engine."""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
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
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DataValidationError, NotFoundError
from app.database.models.dataset import Dataset
from app.database.models.experiment import Experiment, ExperimentRun
from app.database.models.ml_model import MLModel
from app.ml.persistence import save_artifact
from app.ml.preprocessing import FeatureSpec
from app.ml.training import TrainingResult
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
) -> tuple[list[Experiment], int]:
    stmt = select(Experiment).order_by(desc(Experiment.created_at))
    if status:
        stmt = stmt.where(Experiment.status == status)

    total = len(session.scalars(stmt).all())
    items = session.scalars(stmt.offset(offset).limit(limit)).all()
    return list(items), total


def execute_pipeline_run(
    session: Session,
    settings: Settings,
    experiment_id: uuid.UUID,
) -> ExperimentRun:
    experiment = get_experiment(session, experiment_id)
    dataset = get_dataset(session, experiment.dataset_id)

    # Verify dataset reproducibility fingerprint
    if experiment.dataset_fingerprint and dataset.sha256 != experiment.dataset_fingerprint:
        raise DataValidationError(
            f"Dataset fingerprint mismatch: original={experiment.dataset_fingerprint}, current={dataset.sha256}"
        )

    # Create run entry
    run_count = len(experiment.runs)
    run = ExperimentRun(
        experiment_id=experiment.id,
        run_number=run_count + 1,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    experiment.status = "running"
    if not experiment.started_at:
        experiment.started_at = run.started_at
    session.commit()
    session.refresh(run)

    start_time = time.perf_counter()

    try:
        # 1. Dataset Loading
        df = load_dataset_frame(settings, dataset)
        if experiment.target_column not in df.columns:
            raise DataValidationError(f"Target column '{experiment.target_column}' missing from dataset")

        # 2. Feature Selection
        if experiment.selected_features:
            features = [f for f in experiment.selected_features if f in df.columns and f != experiment.target_column]
        else:
            features = [c for c in df.columns if c != experiment.target_column]

        if not features:
            raise DataValidationError("No valid features selected for training")

        # 3. Clean Missing Target Rows
        df = df.dropna(subset=[experiment.target_column])
        X = df[features]
        y = df[experiment.target_column]

        # 4. Train / Val / Test Split (Prevent Data Leakage)
        X_temp, X_test, y_temp, y_test = train_test_split(
            X, y, test_size=experiment.test_size, random_state=experiment.random_state
        )

        val_ratio = experiment.validation_size / (1.0 - experiment.test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp, test_size=val_ratio, random_state=experiment.random_state
        )

        # 5. Preprocessing Pipelines
        numeric_cols = [c for c in features if pd.api.types.is_numeric_dtype(X[c])]
        categorical_cols = [c for c in features if c not in numeric_cols]

        num_transformer = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]
        )
        cat_transformer = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]
        )

        preprocessor = ColumnTransformer(
            transformers=[
                ("num", num_transformer, numeric_cols),
                ("cat", cat_transformer, categorical_cols),
            ]
        )

        # 6. Estimator Setup
        if experiment.problem_type == "classification":
            base_estimator = (
                LogisticRegression(max_iter=500, random_state=experiment.random_state)
                if experiment.algorithm == "linear"
                else RandomForestClassifier(random_state=experiment.random_state)
            )
        else:
            base_estimator = (
                Ridge(random_state=experiment.random_state)
                if experiment.algorithm == "linear"
                else RandomForestRegressor(random_state=experiment.random_state)
            )

        full_pipeline = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("estimator", base_estimator),
            ]
        )

        # 7. Hyperparameter Optimization (Grid / Random Search)
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

            search.fit(X_train, y_train)
            full_pipeline = search.best_estimator_
            best_params = {
                k.replace("estimator__", ""): v for k, v in search.best_params_.items()
            }
            cv_results = {"best_score": float(search.best_score_)}
        else:
            full_pipeline.fit(X_train, y_train)

        # 8. Evaluation on Validation & Test Sets
        val_preds = full_pipeline.predict(X_val)
        test_preds = full_pipeline.predict(X_test)

        if experiment.problem_type == "classification":
            val_metrics = {
                "accuracy": float(accuracy_score(y_val, val_preds)),
                "precision_macro": float(precision_score(y_val, val_preds, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_val, val_preds, average="macro", zero_division=0)),
                "f1_macro": float(f1_score(y_val, val_preds, average="macro", zero_division=0)),
            }
            test_metrics = {
                "accuracy": float(accuracy_score(y_test, test_preds)),
                "precision_macro": float(precision_score(y_test, test_preds, average="macro", zero_division=0)),
                "recall_macro": float(recall_score(y_test, test_preds, average="macro", zero_division=0)),
                "f1_macro": float(f1_score(y_test, test_preds, average="macro", zero_division=0)),
            }
        else:
            val_metrics = {
                "mae": float(mean_absolute_error(y_val, val_preds)),
                "rmse": float(root_mean_squared_error(y_val, val_preds)),
                "r2": float(r2_score(y_val, val_preds)),
            }
            test_metrics = {
                "mae": float(mean_absolute_error(y_test, test_preds)),
                "rmse": float(root_mean_squared_error(y_test, test_preds)),
                "r2": float(r2_score(y_test, test_preds)),
            }

        # 9. Register in MLModel Registry
        duration = time.perf_counter() - start_time
        feature_specs = [
            FeatureSpec(name=col, kind="numeric" if col in numeric_cols else "categorical")
            for col in features
        ]
        import sklearn

        training_result = TrainingResult(
            pipeline=full_pipeline,
            problem_type=experiment.problem_type,
            algorithm=experiment.algorithm,
            target_column=experiment.target_column,
            features=feature_specs,
            class_labels=list(full_pipeline.classes_) if hasattr(full_pipeline, "classes_") else None,
            metrics={"validation": val_metrics, "test": test_metrics},
            metadata={
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_seconds": round(duration, 4),
                "experiment_id": str(experiment.id),
                "run_id": str(run.id),
                "best_hyperparameters": best_params,
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
            target_column=experiment.target_column,
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
        run.completed_at = datetime.now(timezone.utc)
        run.execution_duration_seconds = round(duration, 4)

        experiment.status = "completed"
        experiment.completed_at = run.completed_at
        experiment.execution_duration_seconds = run.execution_duration_seconds

        session.commit()
        session.refresh(run)
        return run

    except Exception as exc:
        duration = time.perf_counter() - start_time
        run.status = "failed"
        run.error_message = str(exc)
        run.completed_at = datetime.now(timezone.utc)
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
    experiment.completed_at = datetime.now(timezone.utc)
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
