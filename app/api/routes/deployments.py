"""Deployment lifecycle management routes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, MLDeployer, MLReader, SettingsDep
from app.repositories.deployments import DeploymentRepository
from app.schemas.common import ErrorResponse
from app.schemas.deployments import DeploymentList, DeploymentRead, DeployRequest
from app.services import audit_service, deployment_service

router = APIRouter(tags=["deployments"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Model or deployment not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Invalid input or data"}}
UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Super Admin role required"}}


@router.post(
    "/models/{model_id}/deploy",
    response_model=DeploymentRead,
    status_code=status.HTTP_200_OK,
    summary="Deploy a trained model to production serving (Super Admin only)",
    responses=NOT_FOUND | UNPROCESSABLE | UNAUTHORIZED | FORBIDDEN,
    
)
def deploy_model(
    model_id: uuid.UUID,
    request: DeployRequest,
    db: DbSession,
    settings: SettingsDep,
    user: MLDeployer,
) -> DeploymentRead:
    deployment = deployment_service.deploy_model(db, settings, model_id, request)
    audit_service.record_standalone(
        db,
        actor=user,
        action="model.deploy",
        category="ml",
        target_type="model",
        target_id=model_id,
        details={"deployment_id": str(deployment.id)},
    )
    return DeploymentRead.model_validate(deployment)


@router.post(
    "/models/{model_id}/undeploy",
    response_model=DeploymentRead,
    status_code=status.HTTP_200_OK,
    summary="Undeploy an active model from production serving (Super Admin only)",
    responses=NOT_FOUND | UNAUTHORIZED | FORBIDDEN,
    
)
def undeploy_model(model_id: uuid.UUID, db: DbSession, user: MLDeployer) -> DeploymentRead:
    deployment = deployment_service.undeploy_model(db, model_id)
    audit_service.record_standalone(
        db,
        actor=user,
        action="model.undeploy",
        category="ml",
        target_type="model",
        target_id=model_id,
        details={"deployment_id": str(deployment.id)},
    )
    return DeploymentRead.model_validate(deployment)


@router.get(
    "/deployments",
    response_model=DeploymentList,
    summary="List all model deployments with pagination",
    responses=UNAUTHORIZED,
)
def list_deployments(
    _user: MLReader,
    db: DbSession,
    model_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DeploymentList:
    repo = DeploymentRepository(db)
    if model_id is not None:
        items = repo.list_for_model(model_id)
        total = len(items)
        items = items[offset : offset + limit]
    else:
        items = repo.list(offset=offset, limit=limit)
        total = repo.count()

    return DeploymentList(
        items=[DeploymentRead.model_validate(d) for d in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Get deployment details by ID",
    responses=NOT_FOUND | UNAUTHORIZED,
)
def get_deployment(deployment_id: uuid.UUID, _user: MLReader, db: DbSession) -> DeploymentRead:
    dep = DeploymentRepository(db).get(deployment_id)
    if not dep:
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"Deployment {deployment_id} not found.")
    return DeploymentRead.model_validate(dep)
