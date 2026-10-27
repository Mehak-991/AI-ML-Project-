"""Model training, metadata and prediction endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, SettingsDep
from app.repositories.ml_models import MLModelRepository
from app.schemas.common import ErrorResponse
from app.schemas.models import ModelList, ModelRead, PredictRequest, PredictResponse, TrainRequest
from app.services import model_service

router = APIRouter(prefix="/models", tags=["models"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Invalid input or data"}}


@router.post(
    "/train",
    response_model=ModelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Train a baseline model on a stored dataset",
    responses=NOT_FOUND | UNPROCESSABLE,
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
    model, predictions, probabilities = model_service.predict_with_model(
        db, settings, model_id, request.records, allow_missing=request.allow_missing
    )
    return PredictResponse(
        model_id=model.id,
        problem_type=model.problem_type,
        predictions=predictions,
        probabilities=probabilities,
    )
