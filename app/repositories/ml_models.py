import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select

from app.database.models import MLModel
from app.repositories.base import BaseRepository


class MLModelRepository(BaseRepository[MLModel]):
    model = MLModel

    def list(  # type: ignore[override]
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[MLModel]:
        """List models newest-first.

        *owner_id* limits to models owned by that user OR unowned legacy
        models (owner_id IS NULL).  Pass ``None`` (admin) to return all.
        """
        stmt = select(MLModel).order_by(MLModel.created_at.desc()).offset(offset).limit(limit)
        if owner_id is not None:
            stmt = stmt.where(or_(MLModel.owner_id == owner_id, MLModel.owner_id.is_(None)))
        return self.session.scalars(stmt).all()

    def count(self, *, owner_id: uuid.UUID | None = None) -> int:  # type: ignore[override]
        stmt = select(func.count()).select_from(MLModel)
        if owner_id is not None:
            stmt = stmt.where(or_(MLModel.owner_id == owner_id, MLModel.owner_id.is_(None)))
        return self.session.scalar(stmt) or 0

    def list_for_dataset(
        self,
        dataset_id: uuid.UUID,
        *,
        owner_id: uuid.UUID | None = None,
    ) -> Sequence[MLModel]:
        stmt = (
            select(MLModel)
            .where(MLModel.dataset_id == dataset_id)
            .order_by(MLModel.created_at.desc())
        )
        if owner_id is not None:
            stmt = stmt.where(or_(MLModel.owner_id == owner_id, MLModel.owner_id.is_(None)))
        return self.session.scalars(stmt).all()

    def next_version(self, name: str) -> int:
        current = self.session.scalar(select(func.max(MLModel.version)).where(MLModel.name == name))
        return (current or 0) + 1
