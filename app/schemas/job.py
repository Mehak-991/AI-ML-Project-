"""Pydantic schemas for Phase 14 Background Jobs & Distributed Task Queue."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled", "retry_pending"]
JobType = Literal[
    "model_training",
    "experiment_execution",
    "batch_prediction",
    "drift_analysis",
    "explainability",
]


class JobCreatePayload(BaseModel):
    job_type: JobType
    model_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    input_config: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=3, ge=0, le=5)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: JobStatus
    created_by_id: uuid.UUID | None = None
    model_id: uuid.UUID | None = None
    experiment_id: uuid.UUID | None = None
    input_config: dict[str, Any]
    progress_percentage: int
    current_stage: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_duration_seconds: float | None = None
    retry_count: int
    max_retries: int
    error_category: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    offset: int
    limit: int


class JobMetricsResponse(BaseModel):
    total_jobs: int
    queued_jobs: int
    running_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
