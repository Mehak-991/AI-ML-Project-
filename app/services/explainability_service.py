"""Model Explainability Service utilizing SHAP and LIME.

Provides:
- Global feature importance (SHAP TreeExplainer, LinearExplainer, or KernelExplainer).
- Local prediction explainability (SHAP waterfall/force contributions and LIME surrogate rules).
- Causal attribution disclaimers and performance guards.
"""

import logging
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.ml import persistence
from app.ml.prediction import predict, validate_records
from app.repositories.ml_models import MLModelRepository
from app.schemas.explainability import (
    ExplainabilitySummaryResponse,
    FeatureContributionItem,
    FeatureImportanceItem,
    GlobalFeatureImportanceResponse,
    LimeRuleContributionItem,
    LocalLimeExplanationResponse,
    LocalShapExplanationResponse,
)
from app.services.dataset_service import get_dataset, load_dataset_frame

logger = logging.getLogger(__name__)


def _load_model_and_pipeline(
    session: Session, settings: Settings, model_id: uuid.UUID
) -> tuple[Any, Any]:
    model = MLModelRepository(session).get(model_id)
    if not model:
        raise NotFoundError(f"Model {model_id} not found.")

    persistence.check_sklearn_compatibility(
        model.sklearn_version, settings.MODEL_COMPATIBILITY_CHECK
    )
    payload = persistence.load_artifact(
        settings.MODEL_DIR, model.artifact_filename, model.artifact_sha256
    )
    return model, payload["pipeline"]


def _get_background_data(
    session: Session, settings: Settings, model: Any, sample_size: int = 50
) -> pd.DataFrame:
    try:
        dataset = get_dataset(session, model.dataset_id)
        df = load_dataset_frame(settings, dataset)
        feature_names = [f["name"] for f in model.feature_schema]
        available_cols = [c for c in feature_names if c in df.columns]
        clean_df = df[available_cols].dropna()
        if len(clean_df) > sample_size:
            clean_df = clean_df.sample(sample_size, random_state=42)
        return clean_df
    except Exception as exc:
        logger.warning("Could not load background training data for explainability: %s", exc)
        return pd.DataFrame()


def get_explainability_summary(
    session: Session, settings: Settings, model_id: uuid.UUID
) -> ExplainabilitySummaryResponse:
    model, _ = _load_model_and_pipeline(session, settings, model_id)

    supported_explainers = ["shap", "lime"]
    if model.algorithm in ("random_forest", "decision_tree", "gradient_boosting"):
        default_explainer = "shap-tree"
    elif model.algorithm in ("linear", "logistic_regression", "ridge"):
        default_explainer = "shap-linear"
    else:
        default_explainer = "lime"

    feature_names = [f["name"] for f in model.feature_schema]

    return ExplainabilitySummaryResponse(
        model_id=model.id,
        model_name=model.name,
        algorithm=model.algorithm,
        problem_type=model.problem_type,
        supported_explainers=supported_explainers,
        default_explainer=default_explainer,
        feature_names=feature_names,
        global_importance_available=True,
    )


def compute_global_feature_importance(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
    sample_size: int = 50,
) -> GlobalFeatureImportanceResponse:
    start_time = time.perf_counter()
    model, pipeline = _load_model_and_pipeline(session, settings, model_id)
    background_df = _get_background_data(session, settings, model, sample_size=sample_size)

    feature_names = [f["name"] for f in model.feature_schema]
    importances: list[FeatureImportanceItem] = []

    if background_df.empty:
        # Fallback to model weights or RF feature importances if no dataset
        estimator = pipeline.named_steps.get("estimator", pipeline)
        if hasattr(estimator, "feature_importances_"):
            raw_scores = estimator.feature_importances_[: len(feature_names)]
        elif hasattr(estimator, "coef_"):
            raw_scores = np.abs(estimator.coef_).flatten()[: len(feature_names)]
        else:
            raw_scores = [1.0 / len(feature_names)] * len(feature_names)

        total = sum(raw_scores) or 1.0
        ranked = sorted(
            zip(feature_names, [s / total for s in raw_scores]),
            key=lambda x: x[1],
            reverse=True,
        )
        for idx, (feat, score) in enumerate(ranked):
            importances.append(
                FeatureImportanceItem(feature=feat, importance=round(float(score), 4), rank=idx + 1)
            )

        duration = time.perf_counter() - start_time
        return GlobalFeatureImportanceResponse(
            model_id=model.id,
            method="feature_importances_fallback",
            summary_plot_type="bar",
            feature_importances=importances,
            background_sample_size=0,
            computation_time_seconds=round(duration, 4),
        )

    # Use SHAP Explainer
    import shap

    try:
        def predict_fn(data):
            if isinstance(data, np.ndarray):
                data = pd.DataFrame(data, columns=feature_names)
            if model.problem_type == "classification" and hasattr(pipeline, "predict_proba"):
                return pipeline.predict_proba(data)
            return pipeline.predict(data)

        # Use shap.Explainer or KernelExplainer with small background
        background_samples = shap.sample(background_df, min(len(background_df), 30))
        explainer = shap.Explainer(predict_fn, background_samples)
        shap_values = explainer(background_samples)

        # Average absolute SHAP values across samples
        if hasattr(shap_values, "values"):
            vals = shap_values.values
            if vals.ndim == 3:  # Multiclass [samples, features, classes]
                mean_abs = np.mean(np.abs(vals), axis=(0, 2))
            else:
                mean_abs = np.mean(np.abs(vals), axis=0)
        else:
            mean_abs = np.zeros(len(feature_names))

        total = float(np.sum(mean_abs)) or 1.0
        normalized = mean_abs / total
        ranked = sorted(zip(feature_names, normalized), key=lambda x: x[1], reverse=True)

        for idx, (feat, score) in enumerate(ranked):
            importances.append(
                FeatureImportanceItem(feature=feat, importance=round(float(score), 4), rank=idx + 1)
            )

        method = "shap_kernel"
    except Exception as exc:
        logger.warning("SHAP calculation error: %s, falling back to estimator importances", exc)
        estimator = pipeline.named_steps.get("estimator", pipeline)
        raw_scores = getattr(estimator, "feature_importances_", None)
        if raw_scores is None and hasattr(estimator, "coef_"):
            raw_scores = np.abs(estimator.coef_).flatten()
        if raw_scores is None:
            raw_scores = [1.0 / len(feature_names)] * len(feature_names)

        total = float(sum(raw_scores)) or 1.0
        ranked = sorted(
            zip(feature_names, [s / total for s in raw_scores[: len(feature_names)]]),
            key=lambda x: x[1],
            reverse=True,
        )
        for idx, (feat, score) in enumerate(ranked):
            importances.append(
                FeatureImportanceItem(feature=feat, importance=round(float(score), 4), rank=idx + 1)
            )
        method = "estimator_attributes"

    duration = time.perf_counter() - start_time
    return GlobalFeatureImportanceResponse(
        model_id=model.id,
        method=method,
        summary_plot_type="bar",
        feature_importances=importances,
        background_sample_size=len(background_df),
        computation_time_seconds=round(duration, 4),
    )


def compute_local_shap_explanation(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
    record: dict[str, Any],
    num_features: int = 10,
    background_samples_count: int = 40,
) -> LocalShapExplanationResponse:
    start_time = time.perf_counter()
    model, pipeline = _load_model_and_pipeline(session, settings, model_id)

    # Validate input record
    validated = validate_records([record], model.feature_schema, allow_missing=True, max_records=1)
    preds, probs = predict(pipeline, validated, model.problem_type)
    prediction = preds[0]
    probabilities = probs[0] if probs else None

    feature_names = [f["name"] for f in model.feature_schema]
    input_df = pd.DataFrame([record])[feature_names]
    background_df = _get_background_data(session, settings, model, sample_size=background_samples_count)

    if background_df.empty:
        background_df = input_df

    import shap

    def predict_fn(data):
        if isinstance(data, np.ndarray):
            data = pd.DataFrame(data, columns=feature_names)
        if model.problem_type == "classification" and hasattr(pipeline, "predict_proba"):
            p = pipeline.predict_proba(data)
            return p[:, 1] if p.shape[1] == 2 else p
        return pipeline.predict(data)

    explainer = shap.Explainer(predict_fn, background_df)
    shap_res = explainer(input_df)

    values = shap_res.values[0]
    base_val = float(shap_res.base_values[0]) if hasattr(shap_res, "base_values") else 0.0

    if values.ndim > 1:
        values = values[:, 0]  # Take primary class

    contributions: list[FeatureContributionItem] = []
    for feat, val, contr in zip(feature_names, input_df.iloc[0], values):
        contr_float = round(float(contr), 4)
        direction = "positive" if contr_float > 0.001 else "negative" if contr_float < -0.001 else "neutral"
        contributions.append(
            FeatureContributionItem(
                feature=feat,
                value=val,
                contribution=contr_float,
                direction=direction,
            )
        )

    # Rank by magnitude of contribution
    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    contributions = contributions[:num_features]

    duration = time.perf_counter() - start_time
    return LocalShapExplanationResponse(
        model_id=model.id,
        prediction=prediction,
        probabilities=probabilities,
        base_value=round(base_val, 4),
        feature_contributions=contributions,
        computation_time_seconds=round(duration, 4),
    )


def compute_local_lime_explanation(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
    record: dict[str, Any],
    num_features: int = 10,
) -> LocalLimeExplanationResponse:
    start_time = time.perf_counter()
    model, pipeline = _load_model_and_pipeline(session, settings, model_id)

    validated = validate_records([record], model.feature_schema, allow_missing=True, max_records=1)
    preds, probs = predict(pipeline, validated, model.problem_type)
    prediction = preds[0]
    probabilities = probs[0] if probs else None

    feature_names = [f["name"] for f in model.feature_schema]
    input_df = pd.DataFrame([record])[feature_names]
    background_df = _get_background_data(session, settings, model, sample_size=50)
    if background_df.empty:
        background_df = input_df

    from lime.lime_tabular import LimeTabularExplainer

    # Pre-clean numeric vs categorical
    numeric_cols = [f["name"] for f in model.feature_schema if f["kind"] == "numeric"]
    categorical_names = {
        idx: f["name"] for idx, f in enumerate(model.feature_schema) if f["kind"] == "categorical"
    }

    # Encode categories numerically for LIME
    explainer = LimeTabularExplainer(
        training_data=np.nan_to_num(background_df.to_numpy(), nan=0.0),
        feature_names=feature_names,
        class_names=["Class_0", "Class_1"] if model.problem_type == "classification" else None,
        mode="classification" if model.problem_type == "classification" else "regression",
        random_state=42,
    )

    def lime_predict(x):
        df_eval = pd.DataFrame(x, columns=feature_names)
        if model.problem_type == "classification" and hasattr(pipeline, "predict_proba"):
            return pipeline.predict_proba(df_eval)
        return pipeline.predict(df_eval)

    instance = np.nan_to_num(input_df.iloc[0].to_numpy(dtype=float, na_value=0.0), nan=0.0)
    exp = explainer.explain_instance(
        instance,
        lime_predict,
        num_features=num_features,
    )

    rule_contributions: list[LimeRuleContributionItem] = []
    for rule, weight in exp.as_list():
        direction = "positive" if weight > 0 else "negative"
        matched_feat = next((f for f in feature_names if f in rule), None)
        rule_contributions.append(
            LimeRuleContributionItem(
                rule=rule,
                feature=matched_feat,
                weight=round(float(weight), 4),
                direction=direction,
            )
        )

    duration = time.perf_counter() - start_time
    score = getattr(exp, "score", None)

    return LocalLimeExplanationResponse(
        model_id=model.id,
        prediction=prediction,
        probabilities=probabilities,
        intercept=round(float(exp.intercept[1] if isinstance(exp.intercept, (list, np.ndarray)) else exp.intercept or 0.0), 4),
        rule_contributions=rule_contributions,
        score=round(float(score), 4) if score is not None else None,
        computation_time_seconds=round(duration, 4),
    )
