"""Production monitoring routes for model health, latency, and prediction throughput."""

import uuid

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.deployments import ModelMonitoringResponse, MonitoringOverviewResponse
from app.services import deployment_service

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Model not found"}}


@router.get(
    "/overview",
    response_model=MonitoringOverviewResponse,
    summary="Get aggregated production monitoring KPIs",
)
def get_monitoring_overview(db: DbSession) -> MonitoringOverviewResponse:
    return deployment_service.get_monitoring_overview(db)


@router.get(
    "/models/{model_id}",
    response_model=ModelMonitoringResponse,
    summary="Get model-level prediction telemetry and production evaluation",
    responses=NOT_FOUND,
)
def get_model_monitoring(model_id: uuid.UUID, db: DbSession) -> ModelMonitoringResponse:
    return deployment_service.get_model_monitoring(db, model_id)
