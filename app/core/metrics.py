"""Prometheus-compatible OpenMetrics exposition engine.

Generates standard Prometheus text-format metrics from database state,
worker status, request counters, and inference latency without adding
heavy third-party dependencies.
"""

from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.deployment import PredictionLog
from app.database.models.job import Job
from app.database.models.ml_model import MLModel


def format_prometheus_metric(
    name: str,
    metric_type: str,
    help_text: str,
    samples: list[tuple[dict[str, str], float | int]],
) -> str:
    """Format metric family into Prometheus text format."""
    lines = [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} {metric_type}",
    ]
    for labels, value in samples:
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")
    return "\n".join(lines) + "\n"


def collect_prometheus_metrics(session: Session) -> str:
    """Collect current platform metrics and format into Prometheus text representation."""
    metrics_output = []

    # 1. Total Models
    total_models = session.scalar(select(func.count(MLModel.id))) or 0
    metrics_output.append(
        format_prometheus_metric(
            "aiml_models_total",
            "gauge",
            "Total number of registered machine learning models.",
            [({}, total_models)],
        )
    )

    # 2. Jobs by Status
    job_statuses = ["queued", "running", "completed", "failed", "cancelled", "retry_pending"]
    job_status_counts = dict(
        session.execute(
            select(Job.status, func.count(Job.id)).group_by(Job.status)
        ).all()
    )
    job_samples = [
        ({"status": status}, job_status_counts.get(status, 0))
        for status in job_statuses
    ]
    metrics_output.append(
        format_prometheus_metric(
            "aiml_jobs_by_status",
            "gauge",
            "Current count of background jobs partitioned by execution status.",
            job_samples,
        )
    )

    # 3. Prediction Log Counters
    prediction_stats = session.execute(
        select(
            PredictionLog.status,
            func.count(PredictionLog.id),
            func.coalesce(func.sum(PredictionLog.record_count), 0),
            func.coalesce(func.avg(PredictionLog.duration_ms), 0.0),
        ).group_by(PredictionLog.status)
    ).all()

    pred_count_samples = []
    pred_record_samples = []
    pred_latency_samples = []

    for status, count, records, avg_dur in prediction_stats:
        pred_count_samples.append(({"status": status}, count))
        pred_record_samples.append(({"status": status}, records))
        pred_latency_samples.append(({"status": status}, round(float(avg_dur), 2)))

    metrics_output.append(
        format_prometheus_metric(
            "aiml_predictions_total",
            "counter",
            "Total prediction requests processed.",
            pred_count_samples or [({"status": "none"}, 0)],
        )
    )
    metrics_output.append(
        format_prometheus_metric(
            "aiml_prediction_records_total",
            "counter",
            "Total individual records predicted across all requests.",
            pred_record_samples or [({"status": "none"}, 0)],
        )
    )
    metrics_output.append(
        format_prometheus_metric(
            "aiml_prediction_duration_ms_avg",
            "gauge",
            "Average prediction duration in milliseconds by outcome status.",
            pred_latency_samples or [({"status": "none"}, 0.0)],
        )
    )

    # 4. Worker Heartbeat Metric
    from scripts.check_worker_health import check_worker_health, DEFAULT_HEARTBEAT_FILE
    from pathlib import Path
    worker_healthy, _ = check_worker_health(Path(DEFAULT_HEARTBEAT_FILE), max_age_seconds=30.0)
    metrics_output.append(
        format_prometheus_metric(
            "aiml_worker_health_status",
            "gauge",
            "Background worker heartbeat status (1 = healthy, 0 = stale/dead).",
            [({}, 1 if worker_healthy else 0)],
        )
    )

    return "\n".join(metrics_output)
