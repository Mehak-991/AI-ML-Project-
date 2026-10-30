"""Pydantic schemas for ML experiment configuration, pipeline runs, and comparison."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExperimentStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
SearchStrategy = Literal["none", "grid", "random"]
ProblemType = Literal["classification", "regression"]
Algorithm = Literal["linear", "random_forest"]


class ExperimentBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dataset_id: uuid.UUID
    target_column: str = Field(min_length=1, max_length=255)
    problem_type: ProblemType
    algorithm: Algorithm
    selected_features: list[str] | None = None
    hyperparameter_config: dict[str, Any] = Field(default_factory=dict)
    search_strategy: SearchStrategy = "none"
    cv_folds: int = Field(default=5, ge=2, le=10)
    scoring_metric: str | None = None
    test_size: float = Field(default=0.2, gt=0.0, lt=1.0)
    validation_size: float = Field(default=0.1, ge=0.0, lt=1.0)
    random_state: int = Field(default=42)


class ExperimentCreate(ExperimentBase):
    pass


class ExperimentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    experiment_id: uuid.UUID
    run_number: int
    status: ExperimentStatus
    best_hyperparameters: dict[str, Any] | None = None
    validation_metrics: dict[str, Any] | None = None
    test_metrics: dict[str, Any] | None = None
    cv_results: dict[str, Any] | None = None
    registered_model_id: uuid.UUID | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_duration_seconds: float | None = None
    created_at: datetime


class ExperimentRead(ExperimentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ExperimentStatus
    dataset_fingerprint: str | None = None
    created_by_id: uuid.UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_duration_seconds: float | None = None
    created_at: datetime
    updated_at: datetime
    runs: list[ExperimentRunRead] = Field(default_factory=list)


class ExperimentList(BaseModel):
    items: list[ExperimentRead]
    total: int
    offset: int
    limit: int


class ExperimentCompareItem(BaseModel):
    experiment_id: uuid.UUID
    experiment_name: str
    run_id: uuid.UUID
    algorithm: str
    problem_type: str
    dataset_id: uuid.UUID
    target_column: str
    status: str
    best_hyperparameters: dict[str, Any] | None = None
    validation_metrics: dict[str, Any] | None = None
    test_metrics: dict[str, Any] | None = None
    execution_duration_seconds: float | None = None
    created_at: datetime


class ExperimentComparisonResponse(BaseModel):
    experiments: list[ExperimentCompareItem]
    warnings: list[str] = Field(default_factory=list)
