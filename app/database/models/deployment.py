import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.ml_model import MLModel


class Deployment(TimestampMixin, Base):
    """A deployment configuration and state for an ML model."""

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="Ready", index=True)
    # Draft, Ready, Deployed, Failed, Undeployed
    version: Mapped[int] = mapped_column(Integer, default=1)
    environment: Mapped[str] = mapped_column(String(64), default="production")
    endpoint_url: Mapped[str] = mapped_column(String(255))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    deployed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    undeployed_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    model: Mapped["MLModel"] = relationship(back_populates="deployments")
    predictions: Mapped[list["PredictionLog"]] = relationship(
        back_populates="deployment", cascade="all, delete-orphan"
    )


class PredictionLog(TimestampMixin, Base):
    """Audit log for single-record or batch prediction requests."""

    __tablename__ = "prediction_logs"
    # Newest-first history pages (scanned backward); the composite also serves model_id lookups.
    __table_args__ = (
        Index("ix_prediction_logs_model_id_created_at", "model_id", "created_at"),
        Index("ix_prediction_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ml_models.id", ondelete="CASCADE"))
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    record_count: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    # "success" | "failed"
    problem_type: Mapped[str] = mapped_column(String(32))
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prediction_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    # Ground-truth evaluation foundation
    ground_truth: Mapped[list[Any] | None] = mapped_column(JSONType, nullable=True)
    is_evaluated: Mapped[bool] = mapped_column(Boolean, default=False)
    # User who requested the prediction (NULL for logs written before Phase 20).
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    model: Mapped["MLModel"] = relationship(back_populates="prediction_logs")
    deployment: Mapped["Deployment | None"] = relationship(back_populates="predictions")
