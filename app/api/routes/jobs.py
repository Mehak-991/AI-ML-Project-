"""API routes for Phase 14 Background Jobs, Distributed Task Queue & Job Management."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, DbSession, SettingsDep, require_role
from app.database.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.job import JobCreatePayload, JobListResponse, JobMetricsResponse, JobRead
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Job not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Validation or execution error"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Unauthorized access to job resource"}}

MLEngineerRole = Annotated[User, Depends(require_role("admin", "ml_engineer"))]


@router.post(
    "",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new background job",
    responses=UNPROCESSABLE | FORBIDDEN,
)
def submit_job(
    request: JobCreatePayload,
    db: DbSession,
    settings: SettingsDep,
    user: MLEngineerRole,
) -> JobRead:
    job = job_service.create_job(
        session=db,
        job_type=request.job_type,
        user=user,
        input_config=request.input_config,
        model_id=request.model_id,
        experiment_id=request.experiment_id,
        max_retries=request.max_retries,
    )
    job_service.dispatch_job(job.id, settings)
    return JobRead.model_validate(job)


@router.get(
    "/metrics",
    response_model=JobMetricsResponse,
    summary="Get summary metrics for jobs",
)
def get_job_metrics(
    db: DbSession,
    user: CurrentUserDep,
) -> JobMetricsResponse:
    return job_service.get_job_metrics(session=db, user=user)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List background jobs with filtering and pagination",
)
def list_jobs(
    db: DbSession,
    user: CurrentUserDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query()] = None,
    job_type: Annotated[str | None, Query()] = None,
) -> JobListResponse:
    items, total = job_service.list_jobs(
        session=db,
        user=user,
        offset=offset,
        limit=limit,
        status=status,
        job_type=job_type,
    )
    return JobListResponse(
        items=[JobRead.model_validate(j) for j in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{job_id}",
    response_model=JobRead,
    summary="Get job status and progress",
    responses=NOT_FOUND | FORBIDDEN,
)
def get_job(
    job_id: uuid.UUID,
    db: DbSession,
    user: CurrentUserDep,
) -> JobRead:
    job = job_service.get_job(session=db, job_id=job_id, user=user)
    return JobRead.model_validate(job)


@router.post(
    "/{job_id}/cancel",
    response_model=JobRead,
    summary="Cancel a queued or running job",
    responses=NOT_FOUND | FORBIDDEN | UNPROCESSABLE,
)
def cancel_job(
    job_id: uuid.UUID,
    db: DbSession,
    user: MLEngineerRole,
) -> JobRead:
    job = job_service.cancel_job(session=db, job_id=job_id, user=user)
    return JobRead.model_validate(job)


@router.post(
    "/{job_id}/retry",
    response_model=JobRead,
    summary="Retry a failed or cancelled job",
    responses=NOT_FOUND | FORBIDDEN | UNPROCESSABLE,
)
def retry_job(
    job_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    user: MLEngineerRole,
) -> JobRead:
    job = job_service.retry_job(session=db, settings=settings, job_id=job_id, user=user)
    return JobRead.model_validate(job)


@router.get(
    "/{job_id}/result",
    response_model=dict[str, Any] | None,
    summary="Retrieve job output result",
    responses=NOT_FOUND | FORBIDDEN,
)
def get_job_result(
    job_id: uuid.UUID,
    db: DbSession,
    user: CurrentUserDep,
) -> dict[str, Any] | None:
    job = job_service.get_job(session=db, job_id=job_id, user=user)
    return job.result
