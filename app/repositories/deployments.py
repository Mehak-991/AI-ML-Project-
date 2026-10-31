import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.database.models.deployment import Deployment, PredictionLog
from app.database.models.ml_model import MLModel
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

    @staticmethod
    def _apply_filters(
        stmt: Select,
        *,
        model_id: uuid.UUID | None,
        deployment_id: uuid.UUID | None,
        status: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        visible_to_user_id: uuid.UUID | None,
    ) -> Select:
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
        if visible_to_user_id is not None:
            # Object-level scope: the user's own requests, plus predictions on models they own.
            owned_models = select(MLModel.id).where(MLModel.owner_id == visible_to_user_id)
            stmt = stmt.where(
                or_(
                    PredictionLog.requested_by_id == visible_to_user_id,
                    PredictionLog.model_id.in_(owned_models),
                )
            )
        return stmt

    def list_filtered(
        self,
        *,
        model_id: uuid.UUID | None = None,
        deployment_id: uuid.UUID | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        visible_to_user_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[PredictionLog]:
        stmt = self._apply_filters(
            select(PredictionLog),
            model_id=model_id,
            deployment_id=deployment_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            visible_to_user_id=visible_to_user_id,
        )
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
        visible_to_user_id: uuid.UUID | None = None,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(PredictionLog),
            model_id=model_id,
            deployment_id=deployment_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            visible_to_user_id=visible_to_user_id,
        )
        return self.session.scalar(stmt) or 0
