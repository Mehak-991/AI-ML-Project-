import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.database.models import Dataset
from app.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    model = Dataset

    def list(  # type: ignore[override]
        self, *, offset: int = 0, limit: int = 50, owner_id: uuid.UUID | None = None
    ) -> Sequence[Dataset]:
        """Newest first. *owner_id* limits to that user's and unowned legacy datasets."""
        stmt = select(Dataset).order_by(Dataset.created_at.desc()).offset(offset).limit(limit)
        if owner_id is not None:
            stmt = stmt.where(or_(Dataset.owner_id == owner_id, Dataset.owner_id.is_(None)))
        return self.session.scalars(stmt).all()

    def count(self, *, owner_id: uuid.UUID | None = None) -> int:  # type: ignore[override]
        stmt = select(func.count()).select_from(Dataset)
        if owner_id is not None:
            stmt = stmt.where(or_(Dataset.owner_id == owner_id, Dataset.owner_id.is_(None)))
        return self.session.scalar(stmt) or 0

    def get_by_sha256(self, sha256: str) -> Dataset | None:
        return self.session.scalars(select(Dataset).where(Dataset.sha256 == sha256)).first()
