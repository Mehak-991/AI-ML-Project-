from sqlalchemy import select

from app.database.models import Dataset
from app.repositories.base import BaseRepository


class DatasetRepository(BaseRepository[Dataset]):
    model = Dataset

    def get_by_sha256(self, sha256: str) -> Dataset | None:
        return self.session.scalars(select(Dataset).where(Dataset.sha256 == sha256)).first()
