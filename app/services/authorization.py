"""Object-level authorization for models, datasets, experiments and prediction audit logs.

Policy (mirrors job ownership in job_service):
- admin and superadmin: everything.
- user: models, datasets and experiments they own; prediction logs they requested
  or that were made against a model they own.
- Objects with no owner (created before ownership tracking) remain usable by every
  authenticated user so existing data keeps working.
"""

import uuid

from app.core.exceptions import PermissionDeniedError
from app.database.models.dataset import Dataset
from app.database.models.deployment import PredictionLog
from app.database.models.experiment import Experiment
from app.database.models.ml_model import MLModel
from app.core.permissions import has_full_resource_access
from app.database.models.user import User


def has_full_access(user: User) -> bool:
    """admin and superadmin see and use every managed resource regardless of ownership."""
    return has_full_resource_access(user.role)


def can_access_model(user: User, model: MLModel) -> bool:
    return has_full_access(user) or model.owner_id is None or model.owner_id == user.id


def ensure_model_access(user: User, model: MLModel) -> None:
    if not can_access_model(user, model):
        raise PermissionDeniedError("Access forbidden: you do not have permission to use this model.")


def owner_scope(user: User) -> uuid.UUID | None:
    """User id to scope owned-object queries by, or None for unrestricted (admin or superadmin)."""
    return None if has_full_access(user) else user.id


def ensure_dataset_access(user: User, dataset: Dataset) -> None:
    if not (has_full_access(user) or dataset.owner_id is None or dataset.owner_id == user.id):
        raise PermissionDeniedError(
            "Access forbidden: you do not have permission to use this dataset."
        )


def ensure_experiment_access(user: User, experiment: Experiment) -> None:
    if not (
        has_full_access(user) or experiment.created_by_id is None or experiment.created_by_id == user.id
    ):
        raise PermissionDeniedError(
            "Access forbidden: you do not have permission to use this experiment."
        )


def prediction_log_scope(user: User) -> uuid.UUID | None:
    """User id to scope prediction-log queries by, or None for unrestricted (admin or superadmin)."""
    return None if has_full_access(user) else user.id


def ensure_prediction_log_access(user: User, log: PredictionLog) -> None:
    if has_full_access(user) or log.requested_by_id == user.id:
        return
    if log.model is not None and log.model.owner_id == user.id:
        return
    raise PermissionDeniedError(
        "Access forbidden: you do not have permission to view this prediction record."
    )
