"""Data quality, feature drift, and model performance monitoring routes.

All routes require authentication. Write operations (analyze-drift) are restricted
to admin and ml_engineer roles.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, SettingsDep, require_role
from app.schemas.common import ErrorResponse
from app.schemas.drift import (
    AnalyzeDriftRequest,
    DriftAlertList,
    DriftAlertRead,
    DriftOverviewResponse,
    DriftReportList,
    DriftReportRead,
)
from app.services import drift_service
from app.database.models.user import User

router = APIRouter(prefix="/drift", tags=["drift"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found"}}

# Roles that can trigger analysis
AnalystRole = Annotated[User, Depends(require_role("admin", "ml_engineer"))]


@router.get(
    "/overview",
    response_model=DriftOverviewResponse,
    summary="Cross-model drift & data-quality overview",
)
def get_drift_overview(db: DbSession) -> DriftOverviewResponse:
    """Aggregated drift status and alert counts for all models."""
    return drift_service.get_drift_overview(db)


@router.get(
    "/models/{model_id}/reports",
    response_model=DriftReportList,
    summary="List drift/quality reports for a model",
    responses=NOT_FOUND,
)
def list_drift_reports(
    model_id: uuid.UUID,
    db: DbSession,
    report_type: str | None = Query(default=None, description="Filter: data_quality | feature_drift | performance"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> DriftReportList:
    return drift_service.list_reports(db, model_id, report_type=report_type, offset=offset, limit=limit)


@router.get(
    "/models/{model_id}/alerts",
    response_model=DriftAlertList,
    summary="List drift alerts for a model",
    responses=NOT_FOUND,
)
def list_model_alerts(
    model_id: uuid.UUID,
    db: DbSession,
    severity: str | None = Query(default=None, description="Filter: warning | critical"),
    resolved: bool | None = Query(default=None, description="Filter by resolved status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> DriftAlertList:
    return drift_service.list_alerts(
        db, model_id=model_id, severity=severity, resolved=resolved, offset=offset, limit=limit
    )


@router.get(
    "/alerts",
    response_model=DriftAlertList,
    summary="List all drift alerts (platform-wide)",
)
def list_all_alerts(
    db: DbSession,
    severity: str | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> DriftAlertList:
    return drift_service.list_alerts(
        db, model_id=None, severity=severity, resolved=resolved, offset=offset, limit=limit
    )


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=DriftAlertRead,
    summary="Resolve a drift alert",
    responses=NOT_FOUND,
)
def resolve_alert(
    alert_id: uuid.UUID,
    db: DbSession,
    _user: AnalystRole,
) -> DriftAlertRead:
    alert = drift_service.resolve_alert(db, alert_id)
    return DriftAlertRead.model_validate(alert)


@router.post(
    "/models/{model_id}/analyze-quality",
    response_model=DriftReportRead,
    summary="Trigger on-demand data-quality analysis for a model",
    responses=NOT_FOUND,
)
def analyze_data_quality(
    model_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    _user: AnalystRole,
) -> DriftReportRead:
    """Analyses recent production prediction inputs for missing values, outliers,
    constant columns, schema mismatches, etc."""
    report = drift_service.analyze_data_quality(db, settings, model_id)
    return DriftReportRead.model_validate(report)


@router.post(
    "/models/{model_id}/analyze-drift",
    response_model=DriftReportRead,
    summary="Trigger on-demand feature drift analysis (PSI + KS / Chi²)",
    responses=NOT_FOUND,
)
def analyze_feature_drift(
    model_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    _user: AnalystRole,
    request: AnalyzeDriftRequest = AnalyzeDriftRequest(),
) -> DriftReportRead:
    """Computes PSI, Kolmogorov-Smirnov (numeric), and Chi-square (categorical) drift
    between training reference distribution and production data."""
    report = drift_service.analyze_feature_drift(db, settings, model_id, request)
    return DriftReportRead.model_validate(report)


@router.post(
    "/models/{model_id}/analyze-performance",
    response_model=DriftReportRead,
    summary="Compute production performance from ground-truth labels",
    responses=NOT_FOUND,
)
def analyze_model_performance(
    model_id: uuid.UUID,
    db: DbSession,
    _user: AnalystRole,
) -> DriftReportRead:
    """Requires ground-truth labels submitted via the predictions/history endpoint.
    Computes accuracy/RMSE degradation vs. training-time reference metrics."""
    report = drift_service.analyze_model_performance(db, model_id)
    return DriftReportRead.model_validate(report)
