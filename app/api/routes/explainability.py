"""FastAPI endpoints for Model Explainability (SHAP & LIME)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, MlOperatorDep, PredictAccessDep, ReadAccessDep, SettingsDep
from app.database.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.explainability import (
    ExplainabilitySummaryResponse,
    ExplainPredictionRequest,
    GlobalFeatureImportanceResponse,
    LocalLimeExplanationResponse,
    LocalShapExplanationResponse,
)
from app.services import authorization, explainability_service, model_service

router = APIRouter(prefix="/models/{model_id}/explainability", tags=["explainability"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Model or artifact not found"}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Invalid input record or parameter error"}}

AnalystRole = MlOperatorDep


@router.get(
    "/summary",
    response_model=ExplainabilitySummaryResponse,
    summary="Get explainability capabilities and metadata for a model",
    responses=NOT_FOUND,
)
def get_explainability_summary(
    model_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    user: ReadAccessDep,
) -> ExplainabilitySummaryResponse:
    authorization.ensure_model_access(user, model_service.get_model(db, model_id))
    return explainability_service.get_explainability_summary(db, settings, model_id)


@router.get(
    "/feature-importance",
    response_model=GlobalFeatureImportanceResponse,
    summary="Compute global feature importance via SHAP / estimator weights",
    responses=NOT_FOUND,
)
def get_global_feature_importance(
    model_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    user: ReadAccessDep,
    sample_size: int = Query(default=50, ge=10, le=200),
) -> GlobalFeatureImportanceResponse:
    authorization.ensure_model_access(user, model_service.get_model(db, model_id))
    return explainability_service.compute_global_feature_importance(
        db, settings, model_id, sample_size=sample_size
    )


@router.post(
    "/shap",
    response_model=LocalShapExplanationResponse,
    summary="Compute local prediction explanation using SHAP",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def explain_with_shap(
    model_id: uuid.UUID,
    request: ExplainPredictionRequest,
    db: DbSession,
    settings: SettingsDep,
    user: PredictAccessDep,
) -> LocalShapExplanationResponse:
    authorization.ensure_model_access(user, model_service.get_model(db, model_id))
    return explainability_service.compute_local_shap_explanation(
        session=db,
        settings=settings,
        model_id=model_id,
        record=request.record,
        num_features=request.num_features,
        background_samples_count=request.background_samples,
        target_class=request.target_class,
    )


@router.post(
    "/lime",
    response_model=LocalLimeExplanationResponse,
    summary="Compute local prediction explanation using LIME surrogate model",
    responses=NOT_FOUND | UNPROCESSABLE,
)
def explain_with_lime(
    model_id: uuid.UUID,
    request: ExplainPredictionRequest,
    db: DbSession,
    settings: SettingsDep,
    user: PredictAccessDep,
) -> LocalLimeExplanationResponse:
    authorization.ensure_model_access(user, model_service.get_model(db, model_id))
    return explainability_service.compute_local_lime_explanation(
        session=db,
        settings=settings,
        model_id=model_id,
        record=request.record,
        num_features=request.num_features,
        target_class=request.target_class,
    )
