import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbSession
from app.schemas.common import ErrorResponse
from app.schemas.deployments import ModelMonitoringResponse, MonitoringOverviewResponse
from app.services import deployment_service

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Model not found"}}
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}


@router.get(
    "/overview",
    response_model=MonitoringOverviewResponse,
    summary="Get aggregated production monitoring KPIs",
    responses=UNAUTHORIZED,
)
def get_monitoring_overview(_user: CurrentUserDep, db: DbSession) -> MonitoringOverviewResponse:
    return deployment_service.get_monitoring_overview(db)


@router.get(
    "/models/{model_id}",
    response_model=ModelMonitoringResponse,
    summary="Get model-level prediction telemetry and production evaluation",
    responses=NOT_FOUND | UNAUTHORIZED,
)
def get_model_monitoring(model_id: uuid.UUID, _user: CurrentUserDep, db: DbSession) -> ModelMonitoringResponse:
    return deployment_service.get_model_monitoring(db, model_id)
