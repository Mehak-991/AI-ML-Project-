import datetime
import time
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DataValidationError, NotFoundError
from app.database.models.deployment import Deployment, PredictionLog
from app.database.models.ml_model import MLModel
from app.ml import persistence
from app.repositories.deployments import DeploymentRepository, PredictionLogRepository
from app.repositories.ml_models import MLModelRepository
from app.schemas.deployments import DeployRequest, ModelMonitoringResponse, MonitoringOverviewResponse


def deploy_model(
    session: Session, settings: Settings, model_id: uuid.UUID, request: DeployRequest
) -> Deployment:
    model = MLModelRepository(session).get(model_id)
    if model is None:
        raise NotFoundError(f"Model {model_id} not found.")

    # Verification: check artifacts exist and are loadable
    try:
        persistence.check_sklearn_compatibility(
            model.sklearn_version, settings.MODEL_COMPATIBILITY_CHECK
        )
        payload = persistence.load_artifact(
            settings.MODEL_DIR, model.artifact_filename, model.artifact_sha256
        )
        if "pipeline" not in payload:
            raise DataValidationError("Loaded model artifact does not contain a valid scikit-learn pipeline.")
    except Exception as exc:
        raise DataValidationError(f"Model cannot be deployed: artifact verification failed: {exc}") from exc

    dep_repo = DeploymentRepository(session)
    # Undeploy previous active deployments for this model
    existing_active = dep_repo.get_active_for_model(model_id)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if existing_active:
        existing_active.status = "Undeployed"
        existing_active.undeployed_at = now_iso

    version = dep_repo.next_version(model_id)
    endpoint_url = f"{settings.API_V1_PREFIX}/models/{model_id}/predict"

    deployment = Deployment(
        model_id=model_id,
        status="Deployed",
        version=version,
        environment=request.environment,
        endpoint_url=endpoint_url,
        configuration=request.configuration,
        deployed_at=now_iso,
    )
    dep_repo.add(deployment)
    session.commit()
    session.refresh(deployment)
    return deployment


def undeploy_model(session: Session, model_id: uuid.UUID) -> Deployment:
    dep_repo = DeploymentRepository(session)
    active = dep_repo.get_active_for_model(model_id)
    if not active:
        raise NotFoundError(f"No active deployment found for model {model_id}.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    active.status = "Undeployed"
    active.undeployed_at = now_iso
    session.commit()
    session.refresh(active)
    return active


def log_prediction(
    session: Session,
    *,
    model_id: uuid.UUID,
    deployment_id: uuid.UUID | None,
    record_count: int,
    duration_ms: float,
    status: str,
    problem_type: str,
    error_category: str | None = None,
    error_message: str | None = None,
    prediction_summary: dict[str, Any] | None = None,
) -> PredictionLog:
    """Safe audit logging for prediction execution."""
    try:
        log_entry = PredictionLog(
            model_id=model_id,
            deployment_id=deployment_id,
            record_count=record_count,
            duration_ms=round(duration_ms, 2),
            status=status,
            problem_type=problem_type,
            error_category=error_category,
            error_message=error_message,
            prediction_summary=prediction_summary,
        )
        session.add(log_entry)
        session.commit()
        return log_entry
    except Exception:
        session.rollback()
        # Logging failures must not fail inference
        return None  # type: ignore[return-value]


def attach_ground_truth(
    session: Session, prediction_id: uuid.UUID, ground_truth: list[Any]
) -> PredictionLog:
    log_repo = PredictionLogRepository(session)
    log_entry = log_repo.get(prediction_id)
    if not log_entry:
        raise NotFoundError(f"Prediction log {prediction_id} not found.")

    log_entry.ground_truth = ground_truth
    log_entry.is_evaluated = True
    session.commit()
    session.refresh(log_entry)
    return log_entry


def get_monitoring_overview(session: Session) -> MonitoringOverviewResponse:
    total_models = session.scalar(select(func.count()).select_from(MLModel)) or 0
    dep_repo = DeploymentRepository(session)
    total_deployments = dep_repo.count()
    active_deployments = dep_repo.count_active()

    log_repo = PredictionLogRepository(session)
    total_predictions = log_repo.count()
    successful_predictions = log_repo.count_filtered(status="success")
    failed_predictions = log_repo.count_filtered(status="failed")

    avg_duration = session.scalar(select(func.avg(PredictionLog.duration_ms))) or 0.0
    total_records = session.scalar(select(func.sum(PredictionLog.record_count))) or 0

    one_day_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    recent_volume = log_repo.count_filtered(start_date=one_day_ago)

    return MonitoringOverviewResponse(
        total_models=total_models,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        total_predictions=total_predictions,
        successful_predictions=successful_predictions,
        failed_predictions=failed_predictions,
        average_duration_ms=round(float(avg_duration), 2),
        total_records_processed=int(total_records),
        recent_volume_24h=recent_volume,
    )


def get_model_monitoring(session: Session, model_id: uuid.UUID) -> ModelMonitoringResponse:
    model = MLModelRepository(session).get(model_id)
    if not model:
        raise NotFoundError(f"Model {model_id} not found.")

    dep_repo = DeploymentRepository(session)
    active_dep = dep_repo.get_active_for_model(model_id)

    log_repo = PredictionLogRepository(session)
    total_preds = log_repo.count_filtered(model_id=model_id)
    success_preds = log_repo.count_filtered(model_id=model_id, status="success")
    failed_preds = log_repo.count_filtered(model_id=model_id, status="failed")

    avg_dur = session.scalar(
        select(func.avg(PredictionLog.duration_ms)).where(PredictionLog.model_id == model_id)
    ) or 0.0
    total_recs = session.scalar(
        select(func.sum(PredictionLog.record_count)).where(PredictionLog.model_id == model_id)
    ) or 0

    evaluated_logs = session.scalars(
        select(PredictionLog).where(
            PredictionLog.model_id == model_id, PredictionLog.is_evaluated == True
        )
    ).all()

    evaluated_count = len(evaluated_logs)
    prod_accuracy: float | None = None
    if evaluated_count > 0:
        # Calculate real production accuracy if ground truth was recorded
        matches = 0
        total_samples = 0
        for elog in evaluated_logs:
            if elog.prediction_summary and "predictions" in elog.prediction_summary and elog.ground_truth:
                preds = elog.prediction_summary["predictions"]
                gts = elog.ground_truth
                for p, g in zip(preds, gts):
                    total_samples += 1
                    if str(p) == str(g):
                        matches += 1
        if total_samples > 0:
            prod_accuracy = round(matches / total_samples, 4)

    return ModelMonitoringResponse(
        model_id=model_id,
        total_predictions=total_preds,
        successful_predictions=success_preds,
        failed_predictions=failed_preds,
        average_duration_ms=round(float(avg_dur), 2),
        total_records_processed=int(total_recs),
        active_deployment=active_dep,  # type: ignore[arg-type]
        ground_truth_evaluated_count=evaluated_count,
        production_accuracy=prod_accuracy,
    )
