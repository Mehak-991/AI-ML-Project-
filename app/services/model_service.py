"""Use cases for training models, reading their metadata and predicting."""

import logging
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, TrainingError
from app.database.models import MLModel
from app.ml import persistence
from app.ml.prediction import predict, validate_records
from app.ml.training import TrainingConfig, train_model
from app.ml.validation import validate_dataframe
from app.repositories.ml_models import MLModelRepository
from app.schemas.models import TrainRequest
from app.services.dataset_service import get_dataset, load_dataset_frame

logger = logging.getLogger(__name__)


def train(
    session: Session,
    settings: Settings,
    request: TrainRequest,
    owner_id: uuid.UUID | None = None,
) -> MLModel:
    dataset = get_dataset(session, request.dataset_id)
    frame = load_dataset_frame(settings, dataset)

    report = validate_dataframe(frame, target_column=request.target_column)
    if not report.is_valid:
        raise TrainingError(
            "The dataset is not valid for this target.", details=report.to_dict()["errors"]
        )

    config = TrainingConfig(
        target_column=request.target_column,
        problem_type=request.problem_type,
        algorithm=request.algorithm,
        feature_columns=request.feature_columns,
        exclude_columns=request.exclude_columns,
        test_size=request.test_size,
        validation_size=request.validation_size,
        random_state=request.random_state,
        drop_duplicates=request.drop_duplicates,
    )
    result = train_model(frame, config)
    artifact = persistence.save_artifact(result, settings.MODEL_DIR)

    record = MLModel(
        name=request.name or f"{dataset.name}-{request.target_column}-{result.algorithm}",
        dataset_id=dataset.id,
        problem_type=result.problem_type,
        algorithm=result.algorithm,
        target_column=result.target_column,
        feature_schema=result.feature_schema,
        metrics=result.metrics,
        training_metadata={
            **result.metadata,
            "class_labels": result.class_labels,
            "dataset_sha256": dataset.sha256,
            "validation_warnings": report.to_dict()["warnings"],
        },
        artifact_filename=artifact.filename,
        artifact_sha256=artifact.sha256,
        sklearn_version=result.metadata["versions"]["scikit-learn"],
        owner_id=owner_id,
    )
    repo = MLModelRepository(session)
    try:
        for attempt in range(2):  # a concurrent train of the same name can take our version
            record.version = repo.next_version(record.name)
            try:
                with session.begin_nested():
                    repo.add(record)
                break
            except IntegrityError:
                if attempt == 1:
                    raise
        session.commit()
    except BaseException:
        session.rollback()
        persistence.delete_artifact(settings.MODEL_DIR, artifact.filename)
        raise
    logger.info(
        "Trained model %s v%d (%s/%s)",
        record.name,
        record.version,
        record.problem_type,
        record.algorithm,
    )
    return record


def get_model(session: Session, model_id: uuid.UUID) -> MLModel:
    model = MLModelRepository(session).get(model_id)
    if model is None:
        raise NotFoundError(f"Model {model_id} not found.")
    return model


def predict_with_model(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
    records: list[dict[str, Any]],
    *,
    allow_missing: bool,
) -> tuple[MLModel, list[Any], list[dict[str, float]] | None]:
    model = get_model(session, model_id)
    features = validate_records(
        records,
        model.feature_schema,
        allow_missing=allow_missing,
        max_records=settings.MAX_PREDICTION_RECORDS,
    )
    # Checked from DB metadata *before* unpickling anything.
    persistence.check_sklearn_compatibility(
        model.sklearn_version, settings.MODEL_COMPATIBILITY_CHECK
    )
    payload = persistence.load_artifact(
        settings.MODEL_DIR, model.artifact_filename, model.artifact_sha256
    )
    predictions, probabilities = predict(payload["pipeline"], features, model.problem_type)
    return model, predictions, probabilities
