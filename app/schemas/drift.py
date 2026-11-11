"""Pydantic schemas for data-quality checks, feature drift, and model performance monitoring."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DriftStatus = Literal["normal", "warning", "critical", "insufficient_data"]
AlertSeverity = Literal["warning", "critical"]
ReportType = Literal["data_quality", "feature_drift", "performance"]


# ---------------------------------------------------------------------------
# Data-Quality
# ---------------------------------------------------------------------------


class ColumnQualityResult(BaseModel):
    """Per-column data-quality check result."""

    column: str
    kind: str  # "numeric" | "categorical" | ...
    missing_count: int
    missing_ratio: float
    unique_count: int
    is_constant: bool = False
    has_infinities: bool = False
    outlier_count: int = 0
    outlier_ratio: float = 0.0
    status: DriftStatus = "normal"
    issues: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    """Full dataset data-quality analysis result."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    report_type: ReportType
    overall_status: DriftStatus
    sample_size: int
    summary: str | None = None
    results: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Feature drift
# ---------------------------------------------------------------------------


class FeatureDriftResult(BaseModel):
    """Drift statistics for a single feature."""

    feature: str
    kind: str  # "numeric" | "categorical"
    # Numeric: KS-test + PSI
    ks_statistic: float | None = None
    ks_p_value: float | None = None
    psi: float | None = None
    # Categorical: PSI + Chi-square
    chi2_statistic: float | None = None
    chi2_p_value: float | None = None
    # Status derived from thresholds
    status: DriftStatus = "normal"
    reference_mean: float | None = None
    production_mean: float | None = None
    reference_std: float | None = None
    production_std: float | None = None


class FeatureDriftReport(BaseModel):
    """Full feature-drift analysis for all features of a model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    report_type: ReportType
    overall_status: DriftStatus
    sample_size: int
    summary: str | None = None
    results: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Model performance
# ---------------------------------------------------------------------------


class PerformanceReport(BaseModel):
    """Ground-truth-based production performance metrics."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    report_type: ReportType
    overall_status: DriftStatus
    sample_size: int
    summary: str | None = None
    results: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Unified report (used for list responses)
# ---------------------------------------------------------------------------


class DriftReportRead(BaseModel):
    """Universal drift report schema for list and detail endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    report_type: ReportType
    overall_status: DriftStatus
    sample_size: int
    summary: str | None = None
    results: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DriftReportList(BaseModel):
    items: list[DriftReportRead]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class DriftAlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    drift_report_id: uuid.UUID
    alert_type: ReportType
    severity: AlertSeverity
    feature_name: str | None = None
    metric_name: str | None = None
    metric_value: float | None = None
    threshold: float | None = None
    message: str
    resolved: bool
    created_at: datetime
    updated_at: datetime


class DriftAlertList(BaseModel):
    items: list[DriftAlertRead]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Analyze-drift request (trigger on-demand analysis)
# ---------------------------------------------------------------------------


class AnalyzeDriftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Minimum production samples required before drift is computed
    min_samples: int = Field(default=30, ge=5)
    # PSI threshold for warning / critical
    psi_warning_threshold: float = Field(default=0.1, gt=0)
    psi_critical_threshold: float = Field(default=0.2, gt=0)
    # KS-test p-value threshold
    ks_p_warning_threshold: float = Field(default=0.05, gt=0, le=1)


# ---------------------------------------------------------------------------
# Compact overview for the drift dashboard
# ---------------------------------------------------------------------------


class ModelDriftSummary(BaseModel):
    model_id: uuid.UUID
    model_name: str
    latest_data_quality_status: DriftStatus | None = None
    latest_drift_status: DriftStatus | None = None
    latest_performance_status: DriftStatus | None = None
    active_alert_count: int = 0
    critical_alert_count: int = 0
    last_analyzed_at: datetime | None = None


class DriftOverviewResponse(BaseModel):
    models: list[ModelDriftSummary]
    total_active_alerts: int
    total_critical_alerts: int
    models_with_drift: int
    models_with_critical: int
