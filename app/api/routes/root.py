"""Unversioned endpoints: welcome message and liveness probe."""

from typing import Annotated

import hmac

from fastapi import APIRouter, Depends, Header
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.core.exceptions import AuthenticationError
from app.schemas.common import ErrorResponse, RootResponse
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
    responses={
        200: {
            "content": {"text/plain; version=0.0.4; charset=utf-8": {}},
            "description": "OpenMetrics / Prometheus text representation",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server error",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
        },
    },
)
def get_metrics(
    db: Annotated[Session, Depends(get_db)],
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> PlainTextResponse:
    """Exposes OpenMetrics / Prometheus formatted text metrics for scraper targets.

    When METRICS_AUTH_TOKEN is set, the scraper must send `Authorization: Bearer <token>`.
    """
    expected = settings.METRICS_AUTH_TOKEN
    if expected is not None:
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied.encode(), expected.get_secret_value().encode()):
            raise AuthenticationError("A valid metrics token is required.")
    from app.core.metrics import collect_prometheus_metrics

    metrics_text = collect_prometheus_metrics(db)
    return PlainTextResponse(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

