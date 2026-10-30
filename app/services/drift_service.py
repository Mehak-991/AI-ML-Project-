"""Data quality monitoring, statistical drift detection, and model performance monitoring.

Statistical methods used:
- Numerical features: Kolmogorov-Smirnov test (scipy.stats.ks_2samp) + Population
  Stability Index (PSI).
- Categorical features: Chi-squared test (scipy.stats.chi2_contingency) + PSI.
- Performance: ground-truth-based accuracy / RMSE derived from PredictionLog records.

All computation is done in-process using scikit-learn, scipy (bundled with scikit-learn)
and pandas/numpy, which are already project dependencies.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats  # scipy is a transitive dep of scikit-learn
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.database.models.deployment import PredictionLog
from app.database.models.drift import DriftAlert, DriftReport
from app.database.models.ml_model import MLModel
from app.repositories.ml_models import MLModelRepository
from app.schemas.drift import (
    AnalyzeDriftRequest,
    DriftAlertList,
    DriftAlertRead,
    DriftOverviewResponse,
    DriftReportList,
    DriftReportRead,
    DriftStatus,
    ModelDriftSummary,
)
from app.services.dataset_service import load_dataset_frame, get_dataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PSI helpers
# ---------------------------------------------------------------------------

MIN_PSI_SAMPLES = 10  # do not compute PSI with fewer bins having this count


def _psi_numeric(
    reference: np.ndarray,
    production: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Compute PSI for a numeric feature using reference-derived bin edges."""
    ref_clean = reference[~np.isnan(reference)]
    prod_clean = production[~np.isnan(production)]
    if len(ref_clean) < MIN_PSI_SAMPLES or len(prod_clean) < MIN_PSI_SAMPLES:
        return float("nan")

    # Create bins from reference quantiles
    percentiles = np.linspace(0, 100, n_bins + 1)
    bin_edges = np.percentile(ref_clean, percentiles)
    bin_edges[0] -= 1e-8  # ensure min value is included
    bin_edges[-1] += 1e-8

    ref_counts, _ = np.histogram(ref_clean, bins=bin_edges)
    prod_counts, _ = np.histogram(prod_clean, bins=bin_edges)

    ref_pct = ref_counts / max(len(ref_clean), 1)
    prod_pct = prod_counts / max(len(prod_clean), 1)

    # Avoid log(0) by clipping to small epsilon
    eps = 1e-8
    ref_pct = np.clip(ref_pct, eps, None)
    prod_pct = np.clip(prod_pct, eps, None)

    psi = float(np.sum((prod_pct - ref_pct) * np.log(prod_pct / ref_pct)))
    return round(psi, 6)


def _psi_categorical(
    reference: pd.Series,
    production: pd.Series,
) -> float:
    """Compute PSI for a categorical feature using reference-derived categories."""
    ref_clean = reference.dropna().astype(str)
    prod_clean = production.dropna().astype(str)
    if len(ref_clean) < MIN_PSI_SAMPLES or len(prod_clean) < MIN_PSI_SAMPLES:
        return float("nan")

    categories = ref_clean.unique().tolist()
    eps = 1e-8

    ref_counts = ref_clean.value_counts()
    prod_counts = prod_clean.value_counts()

    psi = 0.0
    for cat in categories:
        ref_p = max(ref_counts.get(cat, 0) / len(ref_clean), eps)
        prod_p = max(prod_counts.get(cat, 0) / len(prod_clean), eps)
        psi += (prod_p - ref_p) * math.log(prod_p / ref_p)

    return round(psi, 6)


# ---------------------------------------------------------------------------
# Status thresholds
# ---------------------------------------------------------------------------


def _drift_status_from_psi(psi: float, warn: float = 0.1, crit: float = 0.2) -> DriftStatus:
    if math.isnan(psi):
        return "insufficient_data"
    if psi >= crit:
        return "critical"
    if psi >= warn:
        return "warning"
    return "normal"


def _drift_status_from_ks(p_value: float, warn_p: float = 0.05) -> DriftStatus:
    if math.isnan(p_value):
        return "insufficient_data"
    # Low p-value means significant drift
    if p_value < warn_p * 0.5:
        return "critical"
    if p_value < warn_p:
        return "warning"
    return "normal"


def _aggregate_statuses(statuses: list[DriftStatus]) -> DriftStatus:
    if not statuses:
        return "insufficient_data"
    if "critical" in statuses:
        return "critical"
    if "warning" in statuses:
        return "warning"
    if all(s == "insufficient_data" for s in statuses):
        return "insufficient_data"
    return "normal"


# ---------------------------------------------------------------------------
# Extract production feature records from PredictionLogs
# ---------------------------------------------------------------------------


def _extract_production_features(
    session: Session, model_id: uuid.UUID, limit: int = 5000
) -> pd.DataFrame | None:
    """Reconstruct a DataFrame of input features from recent PredictionLog summaries."""
    logs = session.scalars(
        select(PredictionLog)
        .where(
            PredictionLog.model_id == model_id,
            PredictionLog.status == "success",
            PredictionLog.prediction_summary.isnot(None),
        )
        .order_by(PredictionLog.created_at.desc())
        .limit(limit)
    ).all()

    rows: list[dict[str, Any]] = []
    for log in logs:
        summary = log.prediction_summary or {}
        input_records = summary.get("input_records")
        if isinstance(input_records, list):
            rows.extend(input_records)

    if not rows:
        return None
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data Quality Analysis
# ---------------------------------------------------------------------------


def analyze_data_quality(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
) -> DriftReport:
    """Run data-quality checks on recent production data and persist a DriftReport."""
    model = MLModelRepository(session).get(model_id)
    if not model:
        raise NotFoundError(f"Model {model_id} not found.")

    prod_df = _extract_production_features(session, model_id)

    if prod_df is None or len(prod_df) == 0:
        report = DriftReport(
            model_id=model_id,
            report_type="data_quality",
            overall_status="insufficient_data",
            results={},
            sample_size=0,
            summary="No production prediction records available for quality analysis.",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    feature_schema = {f["name"]: f["kind"] for f in model.feature_schema}
    column_results: list[dict[str, Any]] = []
    statuses: list[DriftStatus] = []
    alerts_data: list[dict[str, Any]] = []

    # Schema mismatch check
    schema_issues: list[str] = []
    for expected_col in feature_schema:
        if expected_col not in prod_df.columns:
            schema_issues.append(f"Expected column '{expected_col}' missing from production data.")

    duplicate_count = int(prod_df.duplicated().sum())
    total_rows = len(prod_df)

    for col_name, kind in feature_schema.items():
        if col_name not in prod_df.columns:
            col_result = {
                "column": col_name,
                "kind": kind,
                "missing_count": total_rows,
                "missing_ratio": 1.0,
                "unique_count": 0,
                "is_constant": False,
                "has_infinities": False,
                "outlier_count": 0,
                "outlier_ratio": 0.0,
                "status": "critical",
                "issues": [f"Column '{col_name}' is missing from production data."],
            }
            column_results.append(col_result)
            statuses.append("critical")
            alerts_data.append(
                {
                    "alert_type": "data_quality",
                    "severity": "critical",
                    "feature_name": col_name,
                    "metric_name": "missing_column",
                    "metric_value": None,
                    "threshold": None,
                    "message": f"Column '{col_name}' is missing from production data.",
                }
            )
            continue

        series = prod_df[col_name]
        missing_count = int(series.isna().sum())
        missing_ratio = round(missing_count / total_rows, 4) if total_rows > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))
        is_constant = unique_count <= 1 and missing_count < total_rows
        issues: list[str] = []
        col_statuses: list[DriftStatus] = []

        has_infinities = False
        outlier_count = 0
        outlier_ratio = 0.0

        if kind == "numeric":
            arr = pd.to_numeric(series, errors="coerce").values
            finite_mask = np.isfinite(arr)
            inf_mask = np.isinf(arr.astype(float, copy=False))
            has_infinities = bool(inf_mask.any())
            if has_infinities:
                issues.append(f"{int(inf_mask.sum())} infinite values detected.")
                col_statuses.append("warning")

            # IQR-based outlier detection
            finite_vals = arr[finite_mask & ~np.isnan(arr)]
            if len(finite_vals) > 4:
                q1, q3 = np.percentile(finite_vals, [25, 75])
                iqr = q3 - q1
                if iqr > 0:
                    lower = q1 - 3.0 * iqr
                    upper = q3 + 3.0 * iqr
                    outlier_mask = (finite_vals < lower) | (finite_vals > upper)
                    outlier_count = int(outlier_mask.sum())
                    outlier_ratio = round(outlier_count / len(finite_vals), 4)
                    if outlier_ratio > 0.05:
                        issues.append(f"{outlier_count} extreme outliers ({outlier_ratio:.1%}).")
                        col_statuses.append("warning")

        if missing_ratio >= 0.5:
            issues.append(f"{missing_ratio:.0%} values missing.")
            col_statuses.append("critical" if missing_ratio >= 0.8 else "warning")
        elif missing_ratio > 0.1:
            issues.append(f"{missing_ratio:.0%} values missing.")
            col_statuses.append("warning")

        if is_constant:
            issues.append("Column has a single distinct value (constant).")
            col_statuses.append("warning")

        col_status = _aggregate_statuses(col_statuses) if col_statuses else "normal"
        statuses.append(col_status)

        if col_status in ("warning", "critical"):
            for issue in issues:
                alerts_data.append(
                    {
                        "alert_type": "data_quality",
                        "severity": col_status,
                        "feature_name": col_name,
                        "metric_name": "column_quality",
                        "metric_value": missing_ratio,
                        "threshold": 0.5,
                        "message": issue,
                    }
                )

        column_results.append(
            {
                "column": col_name,
                "kind": kind,
                "missing_count": missing_count,
                "missing_ratio": missing_ratio,
                "unique_count": unique_count,
                "is_constant": is_constant,
                "has_infinities": has_infinities,
                "outlier_count": outlier_count,
                "outlier_ratio": outlier_ratio,
                "status": col_status,
                "issues": issues,
            }
        )

    if schema_issues:
        statuses.append("critical")

    overall = _aggregate_statuses(statuses)

    results = {
        "column_results": column_results,
        "schema_issues": schema_issues,
        "duplicate_count": duplicate_count,
        "duplicate_ratio": round(duplicate_count / total_rows, 4) if total_rows > 0 else 0.0,
        "total_rows": total_rows,
    }

    warning_cols = [r["column"] for r in column_results if r["status"] == "warning"]
    critical_cols = [r["column"] for r in column_results if r["status"] == "critical"]
    summary_parts = [f"Analyzed {total_rows} production records."]
    if critical_cols:
        summary_parts.append(f"Critical issues in: {', '.join(critical_cols[:3])}.")
    if warning_cols:
        summary_parts.append(f"Warnings in: {', '.join(warning_cols[:5])}.")
    if duplicate_count:
        summary_parts.append(f"{duplicate_count} duplicate rows detected.")
    if overall == "normal":
        summary_parts.append("No significant data quality issues detected.")
    summary = " ".join(summary_parts)

    report = DriftReport(
        model_id=model_id,
        report_type="data_quality",
        overall_status=overall,
        results=results,
        sample_size=total_rows,
        summary=summary,
    )
    session.add(report)
    session.flush()  # get report.id

    for ad in alerts_data:
        session.add(
            DriftAlert(
                model_id=model_id,
                drift_report_id=report.id,
                alert_type=ad["alert_type"],
                severity=ad["severity"],
                feature_name=ad.get("feature_name"),
                metric_name=ad.get("metric_name"),
                metric_value=ad.get("metric_value"),
                threshold=ad.get("threshold"),
                message=ad["message"],
            )
        )

    session.commit()
    session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Feature Drift Analysis
# ---------------------------------------------------------------------------


def analyze_feature_drift(
    session: Session,
    settings: Settings,
    model_id: uuid.UUID,
    request: AnalyzeDriftRequest,
) -> DriftReport:
    """Compute PSI + KS/Chi2 drift between training reference and production distributions."""
    model = MLModelRepository(session).get(model_id)
    if not model:
        raise NotFoundError(f"Model {model_id} not found.")

    # Load reference (training) dataset
    try:
        dataset = get_dataset(session, model.dataset_id)
        ref_df = load_dataset_frame(settings, dataset)
        # Remove target column from reference
        if model.target_column in ref_df.columns:
            ref_df = ref_df.drop(columns=[model.target_column])
    except Exception as exc:
        logger.warning("Could not load training dataset for model %s: %s", model_id, exc)
        ref_df = None

    prod_df = _extract_production_features(session, model_id)

    if ref_df is None or prod_df is None or len(prod_df) < request.min_samples:
        report = DriftReport(
            model_id=model_id,
            report_type="feature_drift",
            overall_status="insufficient_data",
            results={},
            sample_size=len(prod_df) if prod_df is not None else 0,
            summary=f"Insufficient production data for drift analysis (need ≥{request.min_samples} samples).",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    feature_schema = {f["name"]: f["kind"] for f in model.feature_schema}
    feature_results: list[dict[str, Any]] = []
    statuses: list[DriftStatus] = []
    alerts_data: list[dict[str, Any]] = []

    for feature, kind in feature_schema.items():
        if feature not in ref_df.columns or feature not in prod_df.columns:
            feature_results.append(
                {"feature": feature, "kind": kind, "status": "insufficient_data"}
            )
            statuses.append("insufficient_data")
            continue

        ref_series = ref_df[feature]
        prod_series = prod_df[feature]
        result: dict[str, Any] = {"feature": feature, "kind": kind}

        if kind == "numeric":
            ref_arr = pd.to_numeric(ref_series, errors="coerce").dropna().values
            prod_arr = pd.to_numeric(prod_series, errors="coerce").dropna().values

            if len(ref_arr) >= MIN_PSI_SAMPLES and len(prod_arr) >= MIN_PSI_SAMPLES:
                ks_stat, ks_p = stats.ks_2samp(ref_arr, prod_arr)
                psi = _psi_numeric(ref_arr, prod_arr)

                result["ks_statistic"] = round(float(ks_stat), 6)
                result["ks_p_value"] = round(float(ks_p), 6)
                result["psi"] = psi if not math.isnan(psi) else None
                result["reference_mean"] = round(float(np.mean(ref_arr)), 6)
                result["production_mean"] = round(float(np.mean(prod_arr)), 6)
                result["reference_std"] = round(float(np.std(ref_arr)), 6)
                result["production_std"] = round(float(np.std(prod_arr)), 6)

                # Determine status using PSI (primary) and KS (secondary)
                psi_status = _drift_status_from_psi(
                    psi,
                    warn=request.psi_warning_threshold,
                    crit=request.psi_critical_threshold,
                )
                ks_status = _drift_status_from_ks(ks_p, warn_p=request.ks_p_warning_threshold)
                feat_status = _aggregate_statuses([psi_status, ks_status])
            else:
                feat_status = "insufficient_data"

        else:  # categorical
            ref_s = ref_series.dropna().astype(str)
            prod_s = prod_series.dropna().astype(str)

            if len(ref_s) >= MIN_PSI_SAMPLES and len(prod_s) >= MIN_PSI_SAMPLES:
                psi = _psi_categorical(ref_s, prod_s)

                # Build contingency table for chi-square
                all_cats = set(ref_s.unique()) | set(prod_s.unique())
                ref_counts = {c: int((ref_s == c).sum()) for c in all_cats}
                prod_counts = {c: int((prod_s == c).sum()) for c in all_cats}
                contingency = np.array(
                    [[ref_counts[c], prod_counts[c]] for c in sorted(all_cats)]
                )
                # Chi-square requires no all-zero rows
                valid_mask = contingency.sum(axis=1) > 0
                contingency = contingency[valid_mask]

                try:
                    chi2, chi2_p, _, _ = stats.chi2_contingency(contingency)
                except Exception:
                    chi2, chi2_p = float("nan"), float("nan")

                result["psi"] = psi if not math.isnan(psi) else None
                result["chi2_statistic"] = round(float(chi2), 6) if not math.isnan(chi2) else None
                result["chi2_p_value"] = round(float(chi2_p), 6) if not math.isnan(chi2_p) else None

                psi_status = _drift_status_from_psi(
                    psi,
                    warn=request.psi_warning_threshold,
                    crit=request.psi_critical_threshold,
                )
                feat_status = psi_status
            else:
                feat_status = "insufficient_data"

        result["status"] = feat_status
        feature_results.append(result)
        statuses.append(feat_status)

        if feat_status in ("warning", "critical"):
            psi_val = result.get("psi")
            alerts_data.append(
                {
                    "alert_type": "feature_drift",
                    "severity": feat_status,
                    "feature_name": feature,
                    "metric_name": "psi",
                    "metric_value": psi_val,
                    "threshold": request.psi_warning_threshold
                    if feat_status == "warning"
                    else request.psi_critical_threshold,
                    "message": (
                        f"Feature '{feature}' shows {feat_status} drift "
                        f"(PSI={psi_val:.4f})" if psi_val is not None else f"Feature '{feature}' shows {feat_status} drift."
                    ),
                }
            )

    overall = _aggregate_statuses(statuses)
    drifted = [r["feature"] for r in feature_results if r.get("status") in ("warning", "critical")]
    summary_parts = [f"Analyzed {len(prod_df)} production records vs {len(ref_df)} training records."]
    if drifted:
        summary_parts.append(f"Drift detected in: {', '.join(drifted[:5])}.")
    else:
        summary_parts.append("No significant feature drift detected.")

    report = DriftReport(
        model_id=model_id,
        report_type="feature_drift",
        overall_status=overall,
        results={"feature_results": feature_results},
        sample_size=len(prod_df),
        summary=" ".join(summary_parts),
    )
    session.add(report)
    session.flush()

    for ad in alerts_data:
        session.add(
            DriftAlert(
                model_id=model_id,
                drift_report_id=report.id,
                **ad,
            )
        )

    session.commit()
    session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Model Performance Monitoring
# ---------------------------------------------------------------------------


def analyze_model_performance(session: Session, model_id: uuid.UUID) -> DriftReport:
    """Compute production performance metrics from ground-truth PredictionLog entries."""
    model = MLModelRepository(session).get(model_id)
    if not model:
        raise NotFoundError(f"Model {model_id} not found.")

    evaluated_logs = session.scalars(
        select(PredictionLog).where(
            PredictionLog.model_id == model_id,
            PredictionLog.is_evaluated == True,  # noqa: E712
        )
    ).all()

    if not evaluated_logs:
        report = DriftReport(
            model_id=model_id,
            report_type="performance",
            overall_status="insufficient_data",
            results={},
            sample_size=0,
            summary="No ground-truth data available. Submit ground-truth labels to enable performance monitoring.",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    all_preds: list[Any] = []
    all_ground: list[Any] = []

    for log in evaluated_logs:
        if not log.prediction_summary or not log.ground_truth:
            continue
        preds = log.prediction_summary.get("predictions", [])
        gts = log.ground_truth
        for p, g in zip(preds, gts):
            all_preds.append(p)
            all_ground.append(g)

    sample_size = len(all_preds)
    results: dict[str, Any] = {"sample_size": sample_size}

    if sample_size == 0:
        report = DriftReport(
            model_id=model_id,
            report_type="performance",
            overall_status="insufficient_data",
            results=results,
            sample_size=0,
            summary="Ground-truth labels present but no matching prediction values found.",
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    # Training (reference) metrics
    train_metrics = model.metrics.get("test", model.metrics.get("train", {}))
    status: DriftStatus = "normal"
    alerts_data: list[dict[str, Any]] = []

    if model.problem_type == "classification":
        matches = sum(1 for p, g in zip(all_preds, all_ground) if str(p) == str(g))
        prod_accuracy = round(matches / sample_size, 4)
        ref_accuracy = train_metrics.get("accuracy", None)

        results["production_accuracy"] = prod_accuracy
        results["reference_accuracy"] = ref_accuracy
        results["evaluated_batches"] = len(evaluated_logs)

        if ref_accuracy is not None:
            degradation = ref_accuracy - prod_accuracy
            results["accuracy_degradation"] = round(degradation, 4)
            if degradation >= 0.15:
                status = "critical"
                alerts_data.append(
                    {
                        "alert_type": "performance",
                        "severity": "critical",
                        "feature_name": None,
                        "metric_name": "accuracy_degradation",
                        "metric_value": degradation,
                        "threshold": 0.15,
                        "message": f"Production accuracy degraded by {degradation:.1%} (ref: {ref_accuracy:.1%} → prod: {prod_accuracy:.1%}).",
                    }
                )
            elif degradation >= 0.05:
                status = "warning"
                alerts_data.append(
                    {
                        "alert_type": "performance",
                        "severity": "warning",
                        "feature_name": None,
                        "metric_name": "accuracy_degradation",
                        "metric_value": degradation,
                        "threshold": 0.05,
                        "message": f"Production accuracy slightly degraded by {degradation:.1%} (ref: {ref_accuracy:.1%} → prod: {prod_accuracy:.1%}).",
                    }
                )
        summary = (
            f"Production accuracy: {prod_accuracy:.1%} over {sample_size} labeled samples."
            + (f" Reference accuracy: {ref_accuracy:.1%}." if ref_accuracy else "")
        )

    else:  # regression
        try:
            pred_arr = np.array([float(p) for p in all_preds])
            gt_arr = np.array([float(g) for g in all_ground])
            rmse = float(np.sqrt(np.mean((pred_arr - gt_arr) ** 2)))
            mae = float(np.mean(np.abs(pred_arr - gt_arr)))
            r2 = float(1 - np.sum((gt_arr - pred_arr) ** 2) / max(np.sum((gt_arr - np.mean(gt_arr)) ** 2), 1e-10))
        except (ValueError, TypeError):
            rmse = mae = r2 = float("nan")

        ref_rmse = train_metrics.get("rmse", None)
        results["production_rmse"] = round(rmse, 6) if not math.isnan(rmse) else None
        results["production_mae"] = round(mae, 6) if not math.isnan(mae) else None
        results["production_r2"] = round(r2, 6) if not math.isnan(r2) else None
        results["reference_rmse"] = ref_rmse
        results["evaluated_batches"] = len(evaluated_logs)

        if ref_rmse is not None and not math.isnan(rmse):
            degradation_ratio = (rmse - ref_rmse) / max(ref_rmse, 1e-10)
            results["rmse_degradation_ratio"] = round(degradation_ratio, 4)
            if degradation_ratio >= 0.5:
                status = "critical"
                alerts_data.append(
                    {
                        "alert_type": "performance",
                        "severity": "critical",
                        "feature_name": None,
                        "metric_name": "rmse_degradation_ratio",
                        "metric_value": degradation_ratio,
                        "threshold": 0.5,
                        "message": f"Production RMSE degraded by {degradation_ratio:.0%} vs reference.",
                    }
                )
            elif degradation_ratio >= 0.2:
                status = "warning"
                alerts_data.append(
                    {
                        "alert_type": "performance",
                        "severity": "warning",
                        "feature_name": None,
                        "metric_name": "rmse_degradation_ratio",
                        "metric_value": degradation_ratio,
                        "threshold": 0.2,
                        "message": f"Production RMSE degraded by {degradation_ratio:.0%} vs reference.",
                    }
                )
        summary = (
            f"Production RMSE: {rmse:.4f}, MAE: {mae:.4f}, R²: {r2:.4f} over {sample_size} labeled samples."
            if not math.isnan(rmse)
            else f"Could not compute regression metrics over {sample_size} samples."
        )

    report = DriftReport(
        model_id=model_id,
        report_type="performance",
        overall_status=status,
        results=results,
        sample_size=sample_size,
        summary=summary,
    )
    session.add(report)
    session.flush()

    for ad in alerts_data:
        session.add(
            DriftAlert(
                model_id=model_id,
                drift_report_id=report.id,
                **ad,
            )
        )

    session.commit()
    session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def list_reports(
    session: Session,
    model_id: uuid.UUID,
    report_type: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> DriftReportList:
    query = select(DriftReport).where(DriftReport.model_id == model_id)
    if report_type:
        query = query.where(DriftReport.report_type == report_type)

    total = session.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    items = session.scalars(
        query.order_by(DriftReport.created_at.desc()).offset(offset).limit(limit)
    ).all()

    return DriftReportList(
        items=[DriftReportRead.model_validate(r) for r in items],
        total=total,
        offset=offset,
        limit=limit,
    )


def list_alerts(
    session: Session,
    model_id: uuid.UUID | None = None,
    severity: str | None = None,
    resolved: bool | None = None,
    offset: int = 0,
    limit: int = 50,
) -> DriftAlertList:
    query = select(DriftAlert)
    if model_id is not None:
        query = query.where(DriftAlert.model_id == model_id)
    if severity:
        query = query.where(DriftAlert.severity == severity)
    if resolved is not None:
        query = query.where(DriftAlert.resolved == resolved)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(DriftAlert.created_at.desc()).offset(offset).limit(limit)
    ).all()

    return DriftAlertList(
        items=[DriftAlertRead.model_validate(a) for a in items],
        total=total,
        offset=offset,
        limit=limit,
    )


def get_drift_overview(session: Session) -> DriftOverviewResponse:
    """Aggregated drift dashboard summary across all models."""
    models = session.scalars(select(MLModel)).all()
    summaries: list[ModelDriftSummary] = []

    total_active = 0
    total_critical = 0
    models_with_drift = 0
    models_with_critical = 0

    for model in models:
        active_alert_count = session.scalar(
            select(func.count()).where(
                DriftAlert.model_id == model.id,
                DriftAlert.resolved == False,  # noqa: E712
            )
        ) or 0
        critical_alert_count = session.scalar(
            select(func.count()).where(
                DriftAlert.model_id == model.id,
                DriftAlert.resolved == False,  # noqa: E712
                DriftAlert.severity == "critical",
            )
        ) or 0
        total_active += active_alert_count
        total_critical += critical_alert_count

        def _latest_status(rtype: str) -> DriftStatus | None:
            r = session.scalar(
                select(DriftReport)
                .where(DriftReport.model_id == model.id, DriftReport.report_type == rtype)
                .order_by(DriftReport.created_at.desc())
                .limit(1)
            )
            return r.overall_status if r else None  # type: ignore[return-value]

        dq_status = _latest_status("data_quality")
        drift_status = _latest_status("feature_drift")
        perf_status = _latest_status("performance")

        last_report = session.scalar(
            select(DriftReport)
            .where(DriftReport.model_id == model.id)
            .order_by(DriftReport.created_at.desc())
            .limit(1)
        )
        last_analyzed_at = last_report.created_at if last_report else None

        has_drift = any(
            s in ("warning", "critical") for s in [dq_status, drift_status, perf_status] if s
        )
        has_critical = any(s == "critical" for s in [dq_status, drift_status, perf_status] if s)
        if has_drift:
            models_with_drift += 1
        if has_critical:
            models_with_critical += 1

        summaries.append(
            ModelDriftSummary(
                model_id=model.id,
                model_name=model.name,
                latest_data_quality_status=dq_status,
                latest_drift_status=drift_status,
                latest_performance_status=perf_status,
                active_alert_count=active_alert_count,
                critical_alert_count=critical_alert_count,
                last_analyzed_at=last_analyzed_at,
            )
        )

    return DriftOverviewResponse(
        models=summaries,
        total_active_alerts=total_active,
        total_critical_alerts=total_critical,
        models_with_drift=models_with_drift,
        models_with_critical=models_with_critical,
    )


def resolve_alert(session: Session, alert_id: uuid.UUID) -> DriftAlert:
    alert = session.get(DriftAlert, alert_id)
    if not alert:
        raise NotFoundError(f"Drift alert {alert_id} not found.")
    alert.resolved = True
    session.commit()
    session.refresh(alert)
    return alert
