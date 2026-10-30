"""Schemas for Deployment lifecycle management, prediction audit logging, and production monitoring."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DeploymentStatus = Literal["Draft", "Ready", "Deployed", "Failed", "Undeployed"]
PredictionLogStatus = Literal["success", "failed"]


class DeployRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str = Field(default="production", max_length=64)
    configuration: dict[str, Any] = Field(default_factory=dict)


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    status: DeploymentStatus
    version: int
    environment: str
    endpoint_url: str
    configuration: dict[str, Any]
    deployed_at: str | None = None
    undeployed_at: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DeploymentList(BaseModel):
    items: list[DeploymentRead]
    total: int
    offset: int
    limit: int


class PredictionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_id: uuid.UUID
    deployment_id: uuid.UUID | None = None
    record_count: int
    duration_ms: float
    status: PredictionLogStatus
    problem_type: str
    error_category: str | None = None
    error_message: str | None = None
    prediction_summary: dict[str, Any] | None = None
    is_evaluated: bool = False
    created_at: datetime


class PredictionLogList(BaseModel):
    items: list[PredictionLogRead]
    total: int
    offset: int
    limit: int


class GroundTruthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ground_truth: list[Any] = Field(min_length=1, description="List of actual target labels or numeric values.")


class MonitoringOverviewResponse(BaseModel):
    total_models: int
    total_deployments: int
    active_deployments: int
    total_predictions: int
    successful_predictions: int
    failed_predictions: int
    average_duration_ms: float
    total_records_processed: int
    recent_volume_24h: int


class ModelMonitoringResponse(BaseModel):
    model_id: uuid.UUID
    total_predictions: int
    successful_predictions: int
    failed_predictions: int
    average_duration_ms: float
    total_records_processed: int
    active_deployment: DeploymentRead | None = None
    ground_truth_evaluated_count: int
    production_accuracy: float | None = None
