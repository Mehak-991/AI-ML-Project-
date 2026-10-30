"""Unversioned endpoints: welcome message and liveness probe."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.schemas.common import RootResponse
from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/", response_model=RootResponse, summary="Welcome")
def read_root(settings: SettingsDep) -> RootResponse:
    return RootResponse(
        message=f"Welcome to {settings.APP_NAME}",
        name=settings.APP_NAME,
        version=__version__,
        docs_url="/docs",
        health_url=f"{settings.API_V1_PREFIX}/health",
    )



@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def liveness(settings: SettingsDep) -> HealthResponse:
    return health_service.get_liveness(settings)


@router.get(
    "/metrics",
    summary="Prometheus metrics exporter",
    response_class=PlainTextResponse,
)
def get_metrics(
    db: Annotated[Session, Depends(get_db)],
) -> PlainTextResponse:
    """Exposes OpenMetrics / Prometheus formatted text metrics for scraper targets."""
    from app.core.metrics import collect_prometheus_metrics

    metrics_text = collect_prometheus_metrics(db)
    return PlainTextResponse(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

