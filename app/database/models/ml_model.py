import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.dataset import Dataset
    from app.database.models.deployment import Deployment, PredictionLog
    from app.database.models.drift import DriftAlert, DriftReport


class MLModel(TimestampMixin, Base):
    """A trained model. The joblib artifact lives under MODEL_DIR as `artifact_filename`."""

    __tablename__ = "ml_models"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_ml_models_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    # Increments per name: retraining "churn-model" gives v1, v2, ... (each its own artifact).
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    problem_type: Mapped[str] = mapped_column(String(32))
    algorithm: Mapped[str] = mapped_column(String(64))
    target_column: Mapped[str] = mapped_column(String(255))
    feature_schema: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType)
    training_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType)
    artifact_filename: Mapped[str] = mapped_column(String(255), unique=True)
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    sklearn_version: Mapped[str] = mapped_column(String(32))
    # Owner for object-level authorization. NULL = created before ownership tracking
    # (Phase 20); such legacy models stay usable by every authenticated user.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    dataset: Mapped["Dataset"] = relationship(back_populates="models")
    deployments: Mapped[list["Deployment"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    prediction_logs: Mapped[list["PredictionLog"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    drift_reports: Mapped[list["DriftReport"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
    drift_alerts: Mapped[list["DriftAlert"]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )
