"""Experiment and ExperimentRun models for automated ML pipelines and tracking."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.dataset import Dataset
    from app.database.models.ml_model import MLModel
    from app.database.models.user import User


class Experiment(Base, TimestampMixin):
    """An ML experiment definition and container for automated pipeline runs."""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_column: Mapped[str] = mapped_column(String(255), nullable=False)
    problem_type: Mapped[str] = mapped_column(String(50), nullable=False)  # classification | regression
    algorithm: Mapped[str] = mapped_column(String(50), nullable=False)  # linear | random_forest

    selected_features: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    hyperparameter_config: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict
    )
    search_strategy: Mapped[str] = mapped_column(String(50), nullable=False, default="none")  # none | grid | random
    cv_folds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    scoring_metric: Mapped[str | None] = mapped_column(String(50), nullable=True)

    test_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    validation_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    random_state: Mapped[int] = mapped_column(Integer, nullable=False, default=42)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending | running | completed | failed | cancelled

    dataset_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    dataset: Mapped[Dataset] = relationship("Dataset", foreign_keys=[dataset_id])
    created_by: Mapped[User | None] = relationship("User", foreign_keys=[created_by_id])
    runs: Mapped[list[ExperimentRun]] = relationship(
        "ExperimentRun", back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentRun(Base, TimestampMixin):
    """An individual execution run of an ML experiment pipeline."""

    __tablename__ = "experiment_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending | running | completed | failed | cancelled

    best_hyperparameters: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    validation_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    test_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    cv_results: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    registered_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ml_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    experiment: Mapped[Experiment] = relationship("Experiment", back_populates="runs")
    registered_model: Mapped[MLModel | None] = relationship("MLModel", foreign_keys=[registered_model_id])
