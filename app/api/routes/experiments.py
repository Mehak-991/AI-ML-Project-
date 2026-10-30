"""API routes for Phase 12 Automated ML Pipelines and Experiment Tracking."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.api.deps import CurrentUserDep, DbSession, SettingsDep, require_role
from app.database.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.experiment import (
    ExperimentComparisonResponse,
    ExperimentCreate,
    ExperimentList,
    ExperimentRead,
    ExperimentRunRead,
)
from app.services import experiment_service

router = APIRouter(prefix="/experiments", tags=["experiments"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Experiment not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Validation or Pipeline execution error"}}

MLEngineerRole = Annotated[User, Depends(require_role("admin", "ml_engineer"))]


@router.post(
    "",
    response_model=ExperimentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ML experiment",
    responses=UNPROCESSABLE,
)
def create_experiment(
    request: ExperimentCreate,
    db: DbSession,
    user: MLEngineerRole,
) -> ExperimentRead:
    exp = experiment_service.create_experiment(
        session=db,
        dataset_id=request.dataset_id,
        name=request.name,
        target_column=request.target_column,
        problem_type=request.problem_type,
        algorithm=request.algorithm,
        user_id=user.id,
        description=request.description,
        selected_features=request.selected_features,
        hyperparameter_config=request.hyperparameter_config,
        search_strategy=request.search_strategy,
        cv_folds=request.cv_folds,
        scoring_metric=request.scoring_metric,
        test_size=request.test_size,
        validation_size=request.validation_size,
        random_state=request.random_state,
    )
    return ExperimentRead.model_validate(exp)


@router.get(
    "",
    response_model=ExperimentList,
    summary="List ML experiments",
)
def list_experiments(
    db: DbSession,
    _user: CurrentUserDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> ExperimentList:
    items, total = experiment_service.list_experiments(
        session=db, offset=offset, limit=limit, status=status
    )
    return ExperimentList(
        items=[ExperimentRead.model_validate(i) for i in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/compare",
    response_model=ExperimentComparisonResponse,
    summary="Compare multiple ML experiments",
)
def compare_experiments(
    experiment_ids: list[uuid.UUID] = Query(...),
    db: DbSession = None,
    _user: CurrentUserDep = None,
) -> ExperimentComparisonResponse:
    res = experiment_service.compare_experiments(db, experiment_ids)
    return ExperimentComparisonResponse.model_validate(res)


@router.get(
    "/{experiment_id}",
    response_model=ExperimentRead,
    summary="Get single experiment details and runs",
    responses=NOT_FOUND,
)
def get_experiment(
    experiment_id: uuid.UUID,
    db: DbSession,
    _user: CurrentUserDep,
) -> ExperimentRead:
    exp = experiment_service.get_experiment(db, experiment_id)
    return ExperimentRead.model_validate(exp)


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRunRead,
    summary="Execute automated ML pipeline for experiment",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def run_experiment(
    experiment_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    _user: MLEngineerRole,
) -> ExperimentRunRead:
    run = experiment_service.execute_pipeline_run(db, settings, experiment_id)
    return ExperimentRunRead.model_validate(run)


@router.post(
    "/{experiment_id}/cancel",
    response_model=ExperimentRead,
    summary="Cancel a pending or running experiment",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def cancel_experiment(
    experiment_id: uuid.UUID,
    db: DbSession,
    _user: MLEngineerRole,
) -> ExperimentRead:
    exp = experiment_service.cancel_experiment(db, experiment_id)
    return ExperimentRead.model_validate(exp)


@router.post(
    "/{experiment_id}/rerun",
    response_model=ExperimentRunRead,
    summary="Rerun a completed or failed experiment",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def rerun_experiment(
    experiment_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    _user: MLEngineerRole,
) -> ExperimentRunRead:
    run = experiment_service.execute_pipeline_run(db, settings, experiment_id)
    return ExperimentRunRead.model_validate(run)
