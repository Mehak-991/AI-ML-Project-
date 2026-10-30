"""Prediction history audit logging and ground-truth foundation routes."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_role
from app.core.exceptions import NotFoundError
from app.repositories.deployments import PredictionLogRepository
from app.schemas.common import ErrorResponse
from app.schemas.deployments import GroundTruthRequest, PredictionLogList, PredictionLogRead
from app.services import deployment_service

router = APIRouter(tags=["predictions"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Prediction log not found"}}
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Admin or ML Engineer privileges required"}}


@router.get(
    "/predictions/history",
    response_model=PredictionLogList,
    summary="List prediction audit history with pagination and filters",
)
def list_prediction_history(
    db: DbSession,
    model_id: uuid.UUID | None = None,
    deployment_id: uuid.UUID | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PredictionLogList:
    repo = PredictionLogRepository(db)
    items = repo.list_filtered(
        model_id=model_id,
        deployment_id=deployment_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
    total = repo.count_filtered(
        model_id=model_id,
        deployment_id=deployment_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return PredictionLogList(
        items=[PredictionLogRead.model_validate(p) for p in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/predictions/history/{prediction_id}",
    response_model=PredictionLogRead,
    summary="Get single prediction audit record by ID",
    responses=NOT_FOUND,
)
def get_prediction_history_item(prediction_id: uuid.UUID, db: DbSession) -> PredictionLogRead:
    repo = PredictionLogRepository(db)
    item = repo.get(prediction_id)
    if not item:
        raise NotFoundError(f"Prediction log {prediction_id} not found.")
    return PredictionLogRead.model_validate(item)


@router.get(
    "/models/{model_id}/predictions/history",
    response_model=PredictionLogList,
    summary="List prediction audit history for a specific model",
)
def list_model_prediction_history(
    model_id: uuid.UUID,
    db: DbSession,
    status: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PredictionLogList:
    repo = PredictionLogRepository(db)
    items = repo.list_filtered(
        model_id=model_id,
        status=status,
        offset=offset,
        limit=limit,
    )
    total = repo.count_filtered(
        model_id=model_id,
        status=status,
    )
    return PredictionLogList(
        items=[PredictionLogRead.model_validate(p) for p in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/predictions/history/{prediction_id}/ground-truth",
    response_model=PredictionLogRead,
    summary="Submit ground-truth labels for production accuracy evaluation (Admin & ML Engineer only)",
    responses=NOT_FOUND | UNAUTHORIZED | FORBIDDEN,
    dependencies=[Depends(require_role("admin", "ml_engineer"))],
)
def submit_ground_truth(
    prediction_id: uuid.UUID,
    request: GroundTruthRequest,
    db: DbSession,
) -> PredictionLogRead:
    updated = deployment_service.attach_ground_truth(db, prediction_id, request.ground_truth)
    return PredictionLogRead.model_validate(updated)
