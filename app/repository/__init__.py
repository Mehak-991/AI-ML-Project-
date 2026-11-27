"""Data-access layer, importable as `app.repository` (the project-structure guide's layout).

The implementations live in `app.repositories`; this package re-exports them so both import
paths refer to the very same classes:

    from app.repository import EmployeeRepository
"""

from app.repositories.base import BaseRepository
from app.repositories.datasets import DatasetRepository
from app.repositories.deployments import DeploymentRepository, PredictionLogRepository
from app.repositories.employees import EmployeeRepository
from app.repositories.ml_models import MLModelRepository
from app.repositories.users import RefreshTokenRepository, UserRepository

__all__ = [
    "BaseRepository",
    "DatasetRepository",
    "DeploymentRepository",
    "EmployeeRepository",
    "MLModelRepository",
    "PredictionLogRepository",
    "RefreshTokenRepository",
    "UserRepository",
]
