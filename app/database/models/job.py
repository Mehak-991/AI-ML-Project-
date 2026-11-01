"""Job ORM model for persistent background task management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.experiment import Experiment
    from app.database.models.ml_model import MLModel
    from app.database.models.user import User


class Job(Base, TimestampMixin):
    """Persistent job entity tracking asynchronous ML tasks, progress, retries and outputs."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # model_training | experiment_execution | batch_prediction | drift_analysis | explainability
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", index=True
    )  # queued | running | completed | failed | cancelled | retry_pending

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("experiments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    input_config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Lease: which process runs the job and when it last proved it is alive.
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    error_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    # Relationships
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_id])
    model: Mapped[MLModel | None] = relationship("MLModel", foreign_keys=[model_id])
    experiment: Mapped[Experiment | None] = relationship("Experiment", foreign_keys=[experiment_id])
