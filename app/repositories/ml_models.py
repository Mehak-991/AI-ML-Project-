import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.database.models import MLModel
from app.repositories.base import BaseRepository


class MLModelRepository(BaseRepository[MLModel]):
    model = MLModel

    def list_for_dataset(self, dataset_id: uuid.UUID) -> Sequence[MLModel]:
        stmt = (
            select(MLModel)
            .where(MLModel.dataset_id == dataset_id)
            .order_by(MLModel.created_at.desc())
        )
        return self.session.scalars(stmt).all()

    def next_version(self, name: str) -> int:
        current = self.session.scalar(select(func.max(MLModel.version)).where(MLModel.name == name))
        return (current or 0) + 1
