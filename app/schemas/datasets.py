"""Dataset request/response schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    kind: Literal["numeric", "categorical", "boolean", "datetime", "text"]


class ValidationIssueSchema(BaseModel):
    code: str
    message: str
    column: str | None = None


class ValidationReportSchema(BaseModel):
    is_valid: bool
    errors: list[ValidationIssueSchema]
    warnings: list[ValidationIssueSchema]


class MissingColumn(BaseModel):
    column: str
    missing_count: int
    missing_ratio: float


class MissingValueSummary(BaseModel):
    total_missing_cells: int
    rows_with_missing: int
    columns: list[MissingColumn]


class DuplicateSummary(BaseModel):
    duplicate_rows: int
    duplicate_ratio: float
    sample_row_indices: list[int]


class ColumnSummary(BaseModel):
    name: str
    dtype: str
    kind: str
    missing_count: int
    missing_ratio: float
    unique_count: int
    infinite_count: int | None = None
    stats: dict[str, Any] | None = None
    top_values: list[dict[str, Any]] | None = None


class DatasetSummary(BaseModel):
    n_rows: int
    n_columns: int
    memory_bytes: int
    columns: list[ColumnSummary]
    missing_values: MissingValueSummary
    duplicates: DuplicateSummary


class DatasetValidationResponse(BaseModel):
    filename: str
    file_format: str
    size_bytes: int
    validation: ValidationReportSchema
    summary: DatasetSummary


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    original_filename: str
    file_format: str
    size_bytes: int
    sha256: str
    n_rows: int
    n_columns: int
    columns: list[ColumnInfo]
    created_at: datetime


class DatasetCreateResponse(BaseModel):
    dataset: DatasetRead
    validation: ValidationReportSchema


class DatasetList(BaseModel):
    items: list[DatasetRead]
    total: int
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
