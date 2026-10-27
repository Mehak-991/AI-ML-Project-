import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.dataset import Dataset


class MLModel(TimestampMixin, Base):
    """A trained model. The joblib artifact lives under MODEL_DIR as `artifact_filename`."""

    __tablename__ = "ml_models"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
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

    dataset: Mapped["Dataset"] = relationship(back_populates="models")
