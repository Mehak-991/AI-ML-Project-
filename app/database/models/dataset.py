import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType

if TYPE_CHECKING:
    from app.database.models.ml_model import MLModel


class Dataset(TimestampMixin, Base):
    """An uploaded tabular file. The file lives under UPLOAD_DIR as `stored_filename`."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    file_format: Mapped[str] = mapped_column(String(16))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    n_rows: Mapped[int] = mapped_column(Integer)
    n_columns: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    # Owner for object-level authorization. NULL = uploaded before ownership tracking;
    # such datasets stay usable by every authenticated user.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    models: Mapped[list["MLModel"]] = relationship(back_populates="dataset")
