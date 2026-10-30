import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.deployment import Deployment, PredictionLog
from app.repositories.base import BaseRepository


class DeploymentRepository(BaseRepository[Deployment]):
    model = Deployment

    def list_for_model(self, model_id: uuid.UUID) -> Sequence[Deployment]:
        stmt = (
            select(Deployment)
            .where(Deployment.model_id == model_id)
            .order_by(Deployment.version.desc())
        )
        return self.session.scalars(stmt).all()

    def get_active_for_model(self, model_id: uuid.UUID) -> Deployment | None:
        stmt = (
            select(Deployment)
            .where(Deployment.model_id == model_id, Deployment.status == "Deployed")
            .order_by(Deployment.version.desc())
        )
        return self.session.scalars(stmt).first()

    def count_active(self) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Deployment).where(Deployment.status == "Deployed")
        ) or 0

    def next_version(self, model_id: uuid.UUID) -> int:
        current = self.session.scalar(
            select(func.max(Deployment.version)).where(Deployment.model_id == model_id)
        )
        return (current or 0) + 1


class PredictionLogRepository(BaseRepository[PredictionLog]):
    model = PredictionLog

    def list_filtered(
        self,
        *,
        model_id: uuid.UUID | None = None,
        deployment_id: uuid.UUID | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[PredictionLog]:
        stmt = select(PredictionLog)
        if model_id is not None:
            stmt = stmt.where(PredictionLog.model_id == model_id)
        if deployment_id is not None:
            stmt = stmt.where(PredictionLog.deployment_id == deployment_id)
        if status is not None:
            stmt = stmt.where(PredictionLog.status == status)
        if start_date is not None:
            stmt = stmt.where(PredictionLog.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(PredictionLog.created_at <= end_date)

        stmt = stmt.order_by(PredictionLog.created_at.desc()).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def count_filtered(
        self,
        *,
        model_id: uuid.UUID | None = None,
        deployment_id: uuid.UUID | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(PredictionLog)
        if model_id is not None:
            stmt = stmt.where(PredictionLog.model_id == model_id)
        if deployment_id is not None:
            stmt = stmt.where(PredictionLog.deployment_id == deployment_id)
        if status is not None:
            stmt = stmt.where(PredictionLog.status == status)
        if start_date is not None:
            stmt = stmt.where(PredictionLog.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(PredictionLog.created_at <= end_date)

        return self.session.scalar(stmt) or 0
