"""Dataset upload, validation and summary endpoints.

Datasets are only ever referenced by ID; clients cannot supply filesystem paths.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.api.deps import DbSession, SettingsDep, require_role
from app.repositories.datasets import DatasetRepository
from app.schemas.common import ErrorResponse
from app.schemas.datasets import (
    DatasetCreateResponse,
    DatasetList,
    DatasetRead,
    DatasetValidationResponse,
)
from app.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])

UPLOAD_ERRORS = {
    400: {"model": ErrorResponse, "description": "Invalid or unparseable file"},
    401: {"model": ErrorResponse, "description": "Authentication required"},
    403: {"model": ErrorResponse, "description": "Admin or ML Engineer privileges required"},
    413: {"model": ErrorResponse, "description": "File too large"},
    415: {"model": ErrorResponse, "description": "Unsupported file type"},
    422: {"model": ErrorResponse, "description": "Data validation failed"},
}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Dataset not found"}}

UploadedFile = Annotated[UploadFile, File(description="A .csv (UTF-8) or .xlsx file.")]


@router.post(
    "/validate",
    response_model=DatasetValidationResponse,
    summary="Validate and summarize a file without storing it",
    responses=UPLOAD_ERRORS,
)
def validate_dataset_file(
    settings: SettingsDep,
    file: UploadedFile,
    target_column: Annotated[str | None, Form(max_length=255)] = None,
) -> DatasetValidationResponse:
    stored, report, summary = dataset_service.validate_upload(
        settings, file.file, file.filename, target_column
    )
    return DatasetValidationResponse(
        filename=stored.original_filename,
        file_format=stored.file_format,
        size_bytes=stored.size_bytes,
        validation=report.to_dict(),
        summary=summary,
    )


@router.post(
    "",
    response_model=DatasetCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and register a dataset (Admin & ML Engineer only)",
    responses=UPLOAD_ERRORS,
    dependencies=[Depends(require_role("admin", "ml_engineer"))],
)
def upload_dataset(
    settings: SettingsDep,
    db: DbSession,
    file: UploadedFile,
    name: Annotated[str | None, Form(max_length=255)] = None,
) -> DatasetCreateResponse:
    dataset, report = dataset_service.create_dataset(db, settings, file.file, file.filename, name)
    return DatasetCreateResponse(
        dataset=DatasetRead.model_validate(dataset), validation=report.to_dict()
    )


@router.get("", response_model=DatasetList, summary="List datasets")
def list_datasets(
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DatasetList:
    repo = DatasetRepository(db)
    items = [DatasetRead.model_validate(d) for d in repo.list(offset=offset, limit=limit)]
    return DatasetList(items=items, total=repo.count(), offset=offset, limit=limit)


@router.get("/{dataset_id}", response_model=DatasetRead, responses=NOT_FOUND)
def get_dataset(dataset_id: uuid.UUID, db: DbSession) -> DatasetRead:
    return DatasetRead.model_validate(dataset_service.get_dataset(db, dataset_id))


@router.get(
    "/{dataset_id}/summary",
    response_model=DatasetValidationResponse,
    summary="Validation report and summary for a stored dataset",
    responses=NOT_FOUND,
)
def get_dataset_summary(
    dataset_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    target_column: Annotated[str | None, Query(max_length=255)] = None,
) -> DatasetValidationResponse:
    dataset = dataset_service.get_dataset(db, dataset_id)
    report, summary = dataset_service.summarize_dataset(settings, dataset, target_column)
    return DatasetValidationResponse(
        filename=dataset.original_filename,
        file_format=dataset.file_format,
        size_bytes=dataset.size_bytes,
        validation=report.to_dict(),
        summary=summary,
    )
