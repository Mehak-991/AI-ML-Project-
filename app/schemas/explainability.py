"""Pydantic schemas for Phase 13 Model Explainability (SHAP & LIME)."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

ExplanationMethod = Literal["shap", "lime", "both"]


class FeatureImportanceItem(BaseModel):
    feature: str
    importance: float
    rank: int


class GlobalFeatureImportanceResponse(BaseModel):
    model_id: uuid.UUID
    method: str
    summary_plot_type: str
    feature_importances: list[FeatureImportanceItem]
    background_sample_size: int
    computation_time_seconds: float


class FeatureContributionItem(BaseModel):
    feature: str
    value: Any
    contribution: float  # Positive: pushes toward positive class/higher value; Negative: pushes lower
    direction: Literal["positive", "negative", "neutral"]


class LocalShapExplanationResponse(BaseModel):
    model_id: uuid.UUID
    prediction: Any
    probabilities: dict[str, float] | None = None
    base_value: float  # Expected model value
    feature_contributions: list[FeatureContributionItem]
    computation_time_seconds: float
    disclaimer: str = (
        "Feature contributions represent statistical model attribution and do not imply causality."
    )


class LimeRuleContributionItem(BaseModel):
    rule: str
    feature: str | None = None
    weight: float
    direction: Literal["positive", "negative"]


class LocalLimeExplanationResponse(BaseModel):
    model_id: uuid.UUID
    prediction: Any
    probabilities: dict[str, float] | None = None
    intercept: float | None = None
    rule_contributions: list[LimeRuleContributionItem]
    score: float | None = None  # Local surrogate R2 or fidelity score
    computation_time_seconds: float
    disclaimer: str = (
        "LIME local approximations represent surrogate decision boundaries and do not imply causality."
    )


class ExplainabilitySummaryResponse(BaseModel):
    model_id: uuid.UUID
    model_name: str
    algorithm: str
    problem_type: str
    supported_explainers: list[str]
    default_explainer: str
    feature_names: list[str]
    global_importance_available: bool


class ExplainPredictionRequest(BaseModel):
    record: dict[str, Any]
    target_class: str | None = None
    num_features: int = Field(default=10, ge=1, le=50)
    background_samples: int = Field(default=50, ge=10, le=200)
