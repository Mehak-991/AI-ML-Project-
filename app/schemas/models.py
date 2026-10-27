"""Model training, metadata and prediction schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProblemType = Literal["classification", "regression"]
Algorithm = Literal["linear", "random_forest"]
FeatureValue = str | int | float | bool | None


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: uuid.UUID
    target_column: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    problem_type: ProblemType | None = Field(
        default=None, description="Omit to infer from the target column."
    )
    algorithm: Algorithm = "linear"
    feature_columns: list[str] | None = Field(
        default=None, description="Explicit feature list. Default: all non-target columns."
    )
    exclude_columns: list[str] = Field(default_factory=list)
    test_size: float = Field(default=0.2, gt=0, lt=0.5)
    validation_size: float = Field(default=0.2, ge=0, lt=0.5)
    random_state: int = Field(default=42, ge=0)
    drop_duplicates: bool = True

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.test_size + self.validation_size >= 0.8:
            raise ValueError("test_size + validation_size must be below 0.8")
        if self.feature_columns is not None and self.target_column in self.feature_columns:
            raise ValueError("target_column must not be listed in feature_columns")
        return self


class FeatureSchemaItem(BaseModel):
    name: str
    kind: Literal["numeric", "categorical"]


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    name: str
    dataset_id: uuid.UUID
    problem_type: ProblemType
    algorithm: Algorithm
    target_column: str
    feature_schema: list[FeatureSchemaItem]
    metrics: dict[str, dict[str, Any]]
    training_metadata: dict[str, Any]
    sklearn_version: str
    created_at: datetime


class ModelList(BaseModel):
    items: list[ModelRead]
    total: int
    offset: int
    limit: int


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[dict[str, FeatureValue]] = Field(
        min_length=1,
        description="One object per row, keyed by feature name (see the model's feature_schema).",
    )
    allow_missing: bool = Field(
        default=False,
        description="If true, null/empty values are imputed as during training.",
    )


class PredictResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: uuid.UUID
    problem_type: ProblemType
    predictions: list[str | int | float | bool | None]
    probabilities: list[dict[str, float]] | None = None
