"""Data quality, feature drift, and model performance monitoring routes.

All routes require authentication and are limited to models the caller may access.
Write operations (analyze-*, resolve) are restricted to admin and ml_engineer roles.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUserDep, DbSession, SettingsDep, require_role
from app.schemas.common import ErrorResponse
from app.schemas.drift import (
    AnalyzeDriftRequest,
    DriftAlertList,
    DriftAlertRead,
    DriftOverviewResponse,
    DriftReportList,
    DriftReportRead,
)
from app.services import authorization, drift_service, model_service
from app.database.models.user import User

router = APIRouter(prefix="/drift", tags=["drift"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Resource not found"}}
AUTH_ERRORS = {
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Not permitted to use this model"},
}

# Roles that can trigger analysis
AnalystRole = Annotated[User, Depends(require_role("admin", "ml_engineer"))]


def _ensure_model_access(db: DbSession, user: User, model_id: uuid.UUID) -> None:
    authorization.ensure_model_access(user, model_service.get_model(db, model_id))


@router.get(
    "/overview",
    response_model=DriftOverviewResponse,
    summary="Cross-model drift & data-quality overview",
    responses=AUTH_ERRORS,
)
def get_drift_overview(user: CurrentUserDep, db: DbSession) -> DriftOverviewResponse:
    """Aggregated drift status and alert counts for the models the caller may access."""
    return drift_service.get_drift_overview(db, owner_id=authorization.owner_scope(user))


@router.get(
    "/models/{model_id}/reports",
    response_model=DriftReportList,
    summary="List drift/quality reports for a model",
    responses=NOT_FOUND | AUTH_ERRORS,
)
def list_drift_reports(
    model_id: uuid.UUID,
    user: CurrentUserDep,
    db: DbSession,
    report_type: str | None = Query(default=None, description="Filter: data_quality | feature_drift | performance"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> DriftReportList:
    _ensure_model_access(db, user, model_id)
    return drift_service.list_reports(db, model_id, report_type=report_type, offset=offset, limit=limit)


@router.get(
    "/models/{model_id}/alerts",
    response_model=DriftAlertList,
    summary="List drift alerts for a model",
    responses=NOT_FOUND | AUTH_ERRORS,
)
def list_model_alerts(
    model_id: uuid.UUID,
    user: CurrentUserDep,
    db: DbSession,
    severity: str | None = Query(default=None, description="Filter: warning | critical"),
    resolved: bool | None = Query(default=None, description="Filter by resolved status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> DriftAlertList:
    _ensure_model_access(db, user, model_id)
    return drift_service.list_alerts(
        db, model_id=model_id, severity=severity, resolved=resolved, offset=offset, limit=limit
    )


@router.get(
    "/alerts",
    response_model=DriftAlertList,
    summary="List drift alerts across the models the caller may access",
    responses=AUTH_ERRORS,
)
def list_all_alerts(
    user: CurrentUserDep,
    db: DbSession,
    severity: str | None = Query(default=None),
    resolved: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> DriftAlertList:
    return drift_service.list_alerts(
        db,
        model_id=None,
        severity=severity,
        resolved=resolved,
        offset=offset,
        limit=limit,
        owner_id=authorization.owner_scope(user),
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
    user: AnalystRole,
) -> DriftAlertRead:
    alert = drift_service.resolve_alert(db, alert_id, user)
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
    user: AnalystRole,
) -> DriftReportRead:
    """Analyses recent production prediction inputs for missing values, outliers,
    constant columns, schema mismatches, etc."""
    _ensure_model_access(db, user, model_id)
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
    user: AnalystRole,
    request: AnalyzeDriftRequest = AnalyzeDriftRequest(),
) -> DriftReportRead:
    """Computes PSI, Kolmogorov-Smirnov (numeric), and Chi-square (categorical) drift
    between training reference distribution and production data."""
    _ensure_model_access(db, user, model_id)
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
    user: AnalystRole,
) -> DriftReportRead:
    """Requires ground-truth labels submitted via the predictions/history endpoint.
    Computes accuracy/RMSE degradation vs. training-time reference metrics."""
    _ensure_model_access(db, user, model_id)
    report = drift_service.analyze_model_performance(db, model_id)
    return DriftReportRead.model_validate(report)
