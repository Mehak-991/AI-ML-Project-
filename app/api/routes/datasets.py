"""Dataset upload, validation and summary endpoints.

Datasets are only ever referenced by ID; clients cannot supply filesystem paths.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUserDep, DbSession, SettingsDep, require_role
from app.database.models.user import User
from app.repositories.datasets import DatasetRepository
from app.schemas.common import ErrorResponse
from app.schemas.datasets import (
    DatasetCreateResponse,
    DatasetList,
    DatasetRead,
    DatasetValidationResponse,
)
from app.services import authorization, dataset_service

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
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}

UploaderRole = Annotated[User, Depends(require_role("admin", "ml_engineer"))]
UploadedFile = Annotated[UploadFile, File(description="A .csv (UTF-8) or .xlsx file.")]


@router.post(
    "/validate",
    response_model=DatasetValidationResponse,
    summary="Validate and summarize a file without storing it (Admin & ML Engineer only)",
    responses=UPLOAD_ERRORS,
)
def validate_dataset_file(
    _user: UploaderRole,
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
)
def upload_dataset(
    user: UploaderRole,
    settings: SettingsDep,
    db: DbSession,
    file: UploadedFile,
    name: Annotated[str | None, Form(max_length=255)] = None,
) -> DatasetCreateResponse:
    dataset, report = dataset_service.create_dataset(
        db, settings, file.file, file.filename, name, owner_id=user.id
    )
    return DatasetCreateResponse(
        dataset=DatasetRead.model_validate(dataset), validation=report.to_dict()
    )


@router.get("", response_model=DatasetList, summary="List datasets",
    responses=UNAUTHORIZED)
def list_datasets(
    user: CurrentUserDep,
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DatasetList:
    repo = DatasetRepository(db)
    owner_id = authorization.owner_scope(user)
    items = repo.list(offset=offset, limit=limit, owner_id=owner_id)
    return DatasetList(
        items=[DatasetRead.model_validate(d) for d in items],
        total=repo.count(owner_id=owner_id),
        offset=offset,
        limit=limit,
    )


@router.get("/{dataset_id}", response_model=DatasetRead,
    responses=NOT_FOUND | UNAUTHORIZED)
def get_dataset(dataset_id: uuid.UUID, user: CurrentUserDep, db: DbSession) -> DatasetRead:
    dataset = dataset_service.get_dataset(db, dataset_id)
    authorization.ensure_dataset_access(user, dataset)
    return DatasetRead.model_validate(dataset)


@router.get(
    "/{dataset_id}/summary",
    response_model=DatasetValidationResponse,
    summary="Validation report and summary for a stored dataset",
    responses=NOT_FOUND | UNAUTHORIZED,
)
def get_dataset_summary(
    dataset_id: uuid.UUID,
    user: CurrentUserDep,
    db: DbSession,
    settings: SettingsDep,
    target_column: Annotated[str | None, Query(max_length=255)] = None,
) -> DatasetValidationResponse:
    dataset = dataset_service.get_dataset(db, dataset_id)
    authorization.ensure_dataset_access(user, dataset)
    report, summary = dataset_service.summarize_dataset(settings, dataset, target_column)
    return DatasetValidationResponse(
        filename=dataset.original_filename,
        file_format=dataset.file_format,
        size_bytes=dataset.size_bytes,
        validation=report.to_dict(),
        summary=summary,
    )
