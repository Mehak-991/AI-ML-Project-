"""Object-level authorization for models and prediction audit logs.

Policy (mirrors job ownership in job_service):
- admin: every model and prediction log.
- other roles: models they own; prediction logs they requested or that were made
  against a model they own.
- Models with no owner (created before ownership tracking) remain usable by every
  authenticated user so existing deployments keep working; an admin can assign an
  owner to restrict them.
"""

import uuid

from app.core.exceptions import PermissionDeniedError
from app.database.models.deployment import PredictionLog
from app.database.models.ml_model import MLModel
from app.database.models.user import User


def is_admin(user: User) -> bool:
    return user.role == "admin"


def can_access_model(user: User, model: MLModel) -> bool:
    return is_admin(user) or model.owner_id is None or model.owner_id == user.id


def ensure_model_access(user: User, model: MLModel) -> None:
    if not can_access_model(user, model):
        raise PermissionDeniedError("Access forbidden: you do not have permission to use this model.")


def prediction_log_scope(user: User) -> uuid.UUID | None:
    """User id to scope prediction-log queries by, or None for unrestricted (admin)."""
    return None if is_admin(user) else user.id


def ensure_prediction_log_access(user: User, log: PredictionLog) -> None:
    if is_admin(user) or log.requested_by_id == user.id:
        return
    if log.model is not None and log.model.owner_id == user.id:
        return
    raise PermissionDeniedError(
        "Access forbidden: you do not have permission to view this prediction record."
    )
