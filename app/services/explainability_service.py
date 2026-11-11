"""Model Explainability Service utilizing SHAP and LIME.

Provides:
- Global feature importance (SHAP TreeExplainer, LinearExplainer, or KernelExplainer).
- Local prediction explainability (SHAP waterfall/force contributions and LIME surrogate rules).
- Causal attribution disclaimers and performance guards.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DataValidationError, NotFoundError
from app.ml import persistence
from app.ml.prediction import predict, validate_records
from app.ml.preprocessing import MISSING_CATEGORY, FeatureSpec, coerce_features
from app.ml.utils import to_python
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

# Bounds on explanation cost (model evaluations scale with these).
GLOBAL_BACKGROUND_ROWS = 20
GLOBAL_EXPLAINED_ROWS = 30
LIME_BACKGROUND_ROWS = 50
LIME_SAMPLES = 2000


def _shap_samples(n_features: int) -> int:
    """Coalitions per explained row: enough for a stable fit without Kernel SHAP's huge default."""
    return min(500, max(100, 2 * n_features + 50))


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
    """Sample of the training data, typed exactly as the pipeline expects. Empty if unavailable."""
    try:
        dataset = get_dataset(session, model.dataset_id)
        df = load_dataset_frame(settings, dataset)
        specs = _feature_specs(model)
        if any(spec.name not in df.columns for spec in specs):
            return pd.DataFrame()
        frame = coerce_features(df, specs)
        if len(frame) > sample_size:
            frame = frame.sample(sample_size, random_state=42)
        return frame
    except Exception as exc:
        logger.warning("Could not load background training data for explainability: %s", exc)
        return pd.DataFrame()


def _feature_specs(model: Any) -> list[FeatureSpec]:
    return [FeatureSpec(f["name"], f["kind"]) for f in model.feature_schema]


class _FeatureCodec:
    """Maps mixed-type feature frames to the all-numeric matrices SHAP and LIME perturb.

    Categories become integer codes and are turned back into strings before the pipeline
    sees them, so explanations run the real preprocessing. Missing numbers are filled with
    the background median; a missing category is its own code and decodes back to NaN.
    """

    def __init__(self, specs: list[FeatureSpec], frames: list[pd.DataFrame]) -> None:
        self.specs = specs
        self.names = [spec.name for spec in specs]
        self.categorical_indices = [i for i, s in enumerate(specs) if s.kind == "categorical"]
        combined = pd.concat(frames, ignore_index=True)
        self.categories: dict[str, list[str]] = {}
        self.medians: dict[str, float] = {}
        for spec in specs:
            if spec.kind == "categorical":
                values = combined[spec.name].dropna().astype(str).unique().tolist()
                self.categories[spec.name] = [MISSING_CATEGORY, *sorted(values)]
            else:
                median = combined[spec.name].median()
                self.medians[spec.name] = 0.0 if pd.isna(median) else float(median)

    def encode(self, frame: pd.DataFrame) -> np.ndarray:
        columns = []
        for spec in self.specs:
            series = frame[spec.name]
            if spec.kind == "categorical":
                lookup = {value: code for code, value in enumerate(self.categories[spec.name])}
                columns.append(series.map(lambda v, lookup=lookup: 0 if pd.isna(v) else lookup[str(v)]))
            else:
                columns.append(series.fillna(self.medians[spec.name]))
        return np.column_stack([np.asarray(c, dtype=float) for c in columns])

    def decode(self, matrix: np.ndarray) -> pd.DataFrame:
        data: dict[str, Any] = {}
        for index, spec in enumerate(self.specs):
            column = matrix[:, index]
            if spec.kind == "categorical":
                labels = self.categories[spec.name]
                # KernelExplainer and LIME only ever draw existing codes; round defensively.
                codes = np.clip(np.rint(column).astype(int), 0, len(labels) - 1)
                decoded = [np.nan if code == 0 else labels[code] for code in codes]
                data[spec.name] = pd.Series(decoded, dtype=object)
            else:
                data[spec.name] = column.astype(float)
        return pd.DataFrame(data, columns=self.names)


def _class_index(pipeline: Any, prediction: Any, target_class: str | None) -> tuple[int, str]:
    """Which probability column to explain: target_class, else the positive class for binary
    models and the predicted class for multiclass ones."""
    labels = [str(to_python(label)) for label in pipeline.classes_]
    if target_class is not None:
        if target_class not in labels:
            raise DataValidationError(
                f"Unknown target_class '{target_class}'.", details={"classes": labels}
            )
        return labels.index(target_class), target_class
    index = 1 if len(labels) == 2 else labels.index(str(to_python(prediction)))
    return index, labels[index]


def _uses_probabilities(model: Any, pipeline: Any) -> bool:
    return model.problem_type == "classification" and hasattr(pipeline, "predict_proba")


@dataclass
class _LocalContext:
    prediction: Any
    probabilities: dict[str, float] | None
    class_index: int | None  # None: explain the raw model output (regression)
    explained_class: str | None
    codec: _FeatureCodec
    record_matrix: np.ndarray
    background_matrix: np.ndarray


def _prepare_local(
    session: Session,
    settings: Settings,
    model: Any,
    pipeline: Any,
    record: dict[str, Any],
    sample_size: int,
    target_class: str | None,
) -> _LocalContext:
    """Shared by SHAP and LIME: validate the record, predict it and set up the codec."""
    validated = validate_records([record], model.feature_schema, allow_missing=True, max_records=1)
    preds, probs = predict(pipeline, validated, model.problem_type)
    background_df = _get_background_data(session, settings, model, sample_size=sample_size)
    if background_df.empty:
        raise DataValidationError(
            "This model's training dataset is unavailable, so local explanations cannot be "
            "computed."
        )
    class_index, explained_class = (None, None)
    if _uses_probabilities(model, pipeline):
        class_index, explained_class = _class_index(pipeline, preds[0], target_class)
    codec = _FeatureCodec(_feature_specs(model), [background_df, validated])
    return _LocalContext(
        prediction=preds[0],
        probabilities=probs[0] if probs else None,
        class_index=class_index,
        explained_class=explained_class,
        codec=codec,
        record_matrix=codec.encode(validated),
        background_matrix=codec.encode(background_df),
    )


def _estimator_importances(pipeline: Any, feature_names: list[str]) -> list[float]:
    """Per-feature weights from the fitted estimator, summing one-hot columns per feature.

    Falls back to uniform weights when the estimator exposes neither attribute.
    """
    steps = pipeline.named_steps
    estimator = steps.get("model") or steps.get("estimator") or pipeline
    raw = getattr(estimator, "feature_importances_", None)
    if raw is None and hasattr(estimator, "coef_"):
        coef = np.abs(np.asarray(estimator.coef_, dtype=float))
        raw = coef.mean(axis=0) if coef.ndim == 2 else coef
    preprocessor = steps.get("preprocess") or steps.get("preprocessor")
    if raw is None or preprocessor is None:
        return [1.0 / len(feature_names)] * len(feature_names)

    transformed_names = [name.split("__")[-1] for name in preprocessor.get_feature_names_out()]
    if len(transformed_names) != len(raw):
        return [1.0 / len(feature_names)] * len(feature_names)
    # Longest name first so a column "age_group" is not credited to a column "age".
    by_length = sorted(feature_names, key=len, reverse=True)
    totals = dict.fromkeys(feature_names, 0.0)
    for name, score in zip(transformed_names, raw, strict=True):
        owner = next(
            (f for f in by_length if name == f or name.startswith(f"{f}_")), None
        )
        if owner is not None:
            totals[owner] += float(score)
    return [totals[name] for name in feature_names]


def _rank_importances(
    feature_names: list[str], scores: Any
) -> list[FeatureImportanceItem]:
    total = float(np.sum(scores)) or 1.0
    ranked = sorted(
        zip(feature_names, [float(s) / total for s in scores], strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    return [
        FeatureImportanceItem(feature=feature, importance=round(score, 4), rank=index + 1)
        for index, (feature, score) in enumerate(ranked)
    ]


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

    if background_df.empty:
        # Fallback to model weights or RF feature importances if no dataset
        duration = time.perf_counter() - start_time
        return GlobalFeatureImportanceResponse(
            model_id=model.id,
            method="feature_importances_fallback",
            summary_plot_type="bar",
            feature_importances=_rank_importances(
                feature_names, _estimator_importances(pipeline, feature_names)
            ),
            background_sample_size=0,
            computation_time_seconds=round(duration, 4),
        )

    # Use SHAP Explainer
    import shap

    try:
        codec = _FeatureCodec(_feature_specs(model), [background_df])
        encoded = codec.encode(background_df)

        def predict_fn(data: np.ndarray) -> np.ndarray:
            frame = codec.decode(data)
            if _uses_probabilities(model, pipeline):
                return pipeline.predict_proba(frame)
            return pipeline.predict(frame)

        # Kernel SHAP cost grows with background x explained rows x samples; keep it bounded.
        reference = shap.sample(encoded, min(len(encoded), GLOBAL_BACKGROUND_ROWS))
        explained = encoded[: min(len(encoded), GLOBAL_EXPLAINED_ROWS)]
        explainer = shap.KernelExplainer(predict_fn, reference)
        values = np.abs(
            np.asarray(
                explainer.shap_values(explained, nsamples=_shap_samples(len(feature_names))),
                dtype=float,
            )
        )
        # Shape is (rows, features) or (rows, features, classes); older shap returns
        # (classes, rows, features). The feature axis is the one sized len(feature_names).
        feature_axis = values.shape.index(len(feature_names), 1 if values.ndim == 2 else 0)
        mean_abs = values.mean(axis=tuple(a for a in range(values.ndim) if a != feature_axis))
        importances = _rank_importances(feature_names, mean_abs)
        method = "shap_kernel"
    except Exception as exc:
        logger.warning("SHAP calculation error: %s, falling back to estimator importances", exc)
        importances = _rank_importances(
            feature_names, _estimator_importances(pipeline, feature_names)
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
    target_class: str | None = None,
) -> LocalShapExplanationResponse:
    start_time = time.perf_counter()
    model, pipeline = _load_model_and_pipeline(session, settings, model_id)
    ctx = _prepare_local(
        session, settings, model, pipeline, record, background_samples_count, target_class
    )
    codec, class_index = ctx.codec, ctx.class_index

    import shap

    def predict_fn(data: np.ndarray) -> np.ndarray:
        frame = codec.decode(data)
        if class_index is not None:
            return pipeline.predict_proba(frame)[:, class_index]
        return pipeline.predict(frame)

    explainer = shap.KernelExplainer(predict_fn, ctx.background_matrix)
    shap_vals = explainer.shap_values(ctx.record_matrix, nsamples=_shap_samples(len(codec.names)))
    values = np.asarray(shap_vals, dtype=float).reshape(-1)
    base_val = float(np.ravel(explainer.expected_value)[0])

    contributions: list[FeatureContributionItem] = []
    for feat, contr in zip(codec.names, values, strict=True):
        contr_float = round(float(contr), 4)
        direction = "positive" if contr_float > 0.001 else "negative" if contr_float < -0.001 else "neutral"
        contributions.append(
            FeatureContributionItem(
                feature=feat,
                value=record.get(feat),
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
        prediction=ctx.prediction,
        probabilities=ctx.probabilities,
        explained_class=ctx.explained_class,
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
    target_class: str | None = None,
) -> LocalLimeExplanationResponse:
    start_time = time.perf_counter()
    model, pipeline = _load_model_and_pipeline(session, settings, model_id)
    ctx = _prepare_local(
        session, settings, model, pipeline, record, LIME_BACKGROUND_ROWS, target_class
    )
    codec, class_index = ctx.codec, ctx.class_index

    from lime.lime_tabular import LimeTabularExplainer

    is_classifier = class_index is not None
    explainer = LimeTabularExplainer(
        training_data=ctx.background_matrix,
        feature_names=codec.names,
        categorical_features=codec.categorical_indices,
        categorical_names={
            index: codec.categories[codec.names[index]] for index in codec.categorical_indices
        },
        class_names=[str(to_python(label)) for label in pipeline.classes_] if is_classifier else None,
        mode="classification" if is_classifier else "regression",
        random_state=42,
    )

    def lime_predict(data: np.ndarray) -> np.ndarray:
        frame = codec.decode(data)
        return pipeline.predict_proba(frame) if is_classifier else pipeline.predict(frame)

    exp = explainer.explain_instance(
        ctx.record_matrix[0],
        lime_predict,
        labels=(class_index,) if is_classifier else (1,),
        num_features=min(num_features, len(codec.names)),
        num_samples=LIME_SAMPLES,
    )
    # LIME files regression results under a dummy label.
    label = class_index if is_classifier else exp.dummy_label

    # Longest name first so a rule on "age_group" is not attributed to a feature "age".
    by_length = sorted(codec.names, key=len, reverse=True)
    rule_contributions: list[LimeRuleContributionItem] = []
    for rule, weight in exp.as_list(label=label):
        direction = "positive" if weight > 0 else "negative"
        matched_feat = next((f for f in by_length if f in rule), None)
        rule_contributions.append(
            LimeRuleContributionItem(
                rule=rule,
                feature=matched_feat,
                weight=round(float(weight), 4),
                direction=direction,
            )
        )

    duration = time.perf_counter() - start_time
    score = exp.score[label] if isinstance(exp.score, dict) else exp.score

    return LocalLimeExplanationResponse(
        model_id=model.id,
        prediction=ctx.prediction,
        probabilities=ctx.probabilities,
        explained_class=ctx.explained_class,
        intercept=round(float(exp.intercept[label]), 4),
        rule_contributions=rule_contributions,
        score=round(float(score), 4) if score is not None else None,
        computation_time_seconds=round(duration, 4),
    )
