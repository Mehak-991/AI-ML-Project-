"""Model training, metadata and prediction endpoints."""

import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, SettingsDep, require_role
from app.repositories.ml_models import MLModelRepository
from app.schemas.common import ErrorResponse
from app.schemas.models import ModelList, ModelRead, PredictRequest, PredictResponse, TrainRequest
from app.services import deployment_service, model_service

router = APIRouter(prefix="/models", tags=["models"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Invalid input or data"}}
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Admin or ML Engineer privileges required"}}


@router.post(
    "/train",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Train a baseline model on a stored dataset (Admin & ML Engineer only)",
    responses=NOT_FOUND | UNPROCESSABLE | UNAUTHORIZED | FORBIDDEN,
    dependencies=[Depends(require_role("admin", "ml_engineer"))],
)
def train_model(request: TrainRequest, db: DbSession, settings: SettingsDep) -> ModelRead:
    # Synchronous: runs in FastAPI's threadpool. Fine for small datasets; see README limits.
    return ModelRead.model_validate(model_service.train(db, settings, request))


@router.get("", response_model=ModelList, summary="List trained models")
def list_models(
    db: DbSession,
    dataset_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ModelList:
    repo = MLModelRepository(db)
    if dataset_id is not None:
        models = repo.list_for_dataset(dataset_id)
        total = len(models)
        models = models[offset : offset + limit]
    else:
        models = repo.list(offset=offset, limit=limit)
        total = repo.count()
    return ModelList(
        items=[ModelRead.model_validate(m) for m in models],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{model_id}",
    response_model=ModelRead,
    summary="Model metadata, feature schema and metrics",
    responses=NOT_FOUND,
)
def get_model(model_id: uuid.UUID, db: DbSession) -> ModelRead:
    return ModelRead.model_validate(model_service.get_model(db, model_id))


@router.post(
    "/{model_id}/predict",
    response_model=PredictResponse,
    summary="Predict with a saved model",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def predict(
    model_id: uuid.UUID, request: PredictRequest, db: DbSession, settings: SettingsDep
) -> PredictResponse:
    start_time = time.perf_counter()
    active_dep = deployment_service.DeploymentRepository(db).get_active_for_model(model_id)
    deployment_id = active_dep.id if active_dep else None

    try:
        model, predictions, probabilities = model_service.predict_with_model(
            db, settings, model_id, request.records, allow_missing=request.allow_missing
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Safe audit log recording (zero impact on successful inference)
        deployment_service.log_prediction(
            db,
            model_id=model.id,
            deployment_id=deployment_id,
            record_count=len(request.records),
            duration_ms=duration_ms,
            status="success",
            problem_type=model.problem_type,
            prediction_summary={"count": len(predictions), "predictions": predictions[:50]},
        )

        return PredictResponse(
            model_id=model.id,
            problem_type=model.problem_type,
            predictions=predictions,
            probabilities=probabilities,
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        # Audit log failed inference
        deployment_service.log_prediction(
            db,
            model_id=model_id,
            deployment_id=deployment_id,
            record_count=len(request.records),
            duration_ms=duration_ms,
            status="failed",
            problem_type="unknown",
            error_category=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        raise
