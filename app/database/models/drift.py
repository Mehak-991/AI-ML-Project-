"""SQLAlchemy models for data-quality reports, drift analysis, and drift alerts."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.ml_model import MLModel


class DriftReport(TimestampMixin, Base):
    """Stores a full drift analysis snapshot for a model at a point in time."""

    __tablename__ = "drift_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True
    )
    # "data_quality" | "feature_drift" | "performance"
    report_type: Mapped[str] = mapped_column(String(32), index=True)
    # "normal" | "warning" | "critical" | "insufficient_data"
    overall_status: Mapped[str] = mapped_column(String(32), default="normal", index=True)
    # JSON payload with per-feature statistics and test results
    results: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # Number of production records analysed
    sample_size: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    model: Mapped["MLModel"] = relationship(back_populates="drift_reports")
    alerts: Mapped[list["DriftAlert"]] = relationship(
        back_populates="drift_report", cascade="all, delete-orphan"
    )


class DriftAlert(TimestampMixin, Base):
    """A deduplicated, actionable alert raised by a drift analysis."""

    __tablename__ = "drift_alerts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True
    )
    drift_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("drift_reports.id", ondelete="CASCADE"), index=True
    )
    # "data_quality" | "feature_drift" | "performance"
    alert_type: Mapped[str] = mapped_column(String(32))
    # "warning" | "critical"
    severity: Mapped[str] = mapped_column(String(16), index=True)
    feature_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metric_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metric_value: Mapped[float | None] = mapped_column(nullable=True)
    threshold: Mapped[float | None] = mapped_column(nullable=True)
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    model: Mapped["MLModel"] = relationship(back_populates="drift_alerts")
    drift_report: Mapped["DriftReport"] = relationship(back_populates="alerts")
