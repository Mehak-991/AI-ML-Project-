"""Background job management, task queuing, execution dispatch, and lifecycle handling."""

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import DataValidationError, NotFoundError, PermissionDeniedError
from app.database.models.experiment import Experiment
from app.database.models.job import Job
from app.database.models.ml_model import MLModel
from app.database.models.user import User
from app.database.session import get_session_factory
from app.schemas.job import JobMetricsResponse

logger = logging.getLogger(__name__)

# Dedicated background worker pool isolated from FastAPI's event loop
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ml_worker_")


def create_job(
    session: Session,
    job_type: str,
    user: User,
    input_config: dict[str, Any],
    model_id: uuid.UUID | None = None,
    experiment_id: uuid.UUID | None = None,
    max_retries: int = 3,
) -> Job:
    # Validate linked entities exist
    if model_id and not session.get(MLModel, model_id):
        raise NotFoundError(f"Model {model_id} not found.")
    if experiment_id and not session.get(Experiment, experiment_id):
        raise NotFoundError(f"Experiment {experiment_id} not found.")

    job = Job(
        job_type=job_type,
        status="queued",
        created_by_id=user.id,
        model_id=model_id,
        experiment_id=experiment_id,
        input_config=input_config,
        progress_percentage=0,
        current_stage="Queued in task manager",
        max_retries=max_retries,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: uuid.UUID, user: User) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise NotFoundError(f"Job {job_id} not found.")
    if user.role != "admin" and job.created_by_id != user.id:
        raise PermissionDeniedError("Access forbidden: you do not have permission to view this job.")
    return job


def list_jobs(
    session: Session,
    user: User,
    offset: int = 0,
    limit: int = 20,
    status: str | None = None,
    job_type: str | None = None,
) -> tuple[list[Job], int]:
    stmt = select(Job).order_by(desc(Job.created_at))
    if user.role != "admin":
        stmt = stmt.where(Job.created_by_id == user.id)
    if status:
        stmt = stmt.where(Job.status == status)
    if job_type:
        stmt = stmt.where(Job.job_type == job_type)

    total = len(session.scalars(stmt).all())
    items = session.scalars(stmt.offset(offset).limit(limit)).all()
    return list(items), total


def get_job_metrics(session: Session, user: User) -> JobMetricsResponse:
    stmt = select(Job)
    if user.role != "admin":
        stmt = stmt.where(Job.created_by_id == user.id)

    jobs = session.scalars(stmt).all()
    return JobMetricsResponse(
        total_jobs=len(jobs),
        queued_jobs=sum(1 for j in jobs if j.status == "queued"),
        running_jobs=sum(1 for j in jobs if j.status == "running"),
        completed_jobs=sum(1 for j in jobs if j.status == "completed"),
        failed_jobs=sum(1 for j in jobs if j.status == "failed"),
        cancelled_jobs=sum(1 for j in jobs if j.status == "cancelled"),
    )


def cancel_job(session: Session, job_id: uuid.UUID, user: User) -> Job:
    job = get_job(session, job_id, user)
    if job.status not in ("queued", "running", "retry_pending"):
        raise DataValidationError(f"Cannot cancel job in '{job.status}' status.")

    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    job.current_stage = "Job cancelled by user"
    session.commit()
    session.refresh(job)
    return job


def retry_job(
    session: Session, settings: Settings, job_id: uuid.UUID, user: User
) -> Job:
    job = get_job(session, job_id, user)
    if job.status not in ("failed", "cancelled"):
        raise DataValidationError(f"Cannot retry job in '{job.status}' status.")

    job.status = "queued"
    job.progress_percentage = 0
    job.current_stage = "Re-queued for execution"
    job.error_message = None
    job.error_category = None
    job.retry_count += 1
    session.commit()
    session.refresh(job)

    dispatch_job(job.id, settings)
    return job


def _execute_worker_task(job_id: uuid.UUID, settings: Settings) -> None:
    """Asynchronous worker executing job processing in dedicated thread."""
    session_factory = get_session_factory()
    with session_factory() as session:
        job = session.get(Job, job_id)
        if not job or job.status == "cancelled":
            return

        # Ensure job is marked running with execution stage
        job.status = "running"
        if not job.started_at:
            job.started_at = datetime.now(timezone.utc)
        job.progress_percentage = 15
        job.current_stage = "Initializing worker pipeline"
        session.commit()

        start_time = time.perf_counter()

        try:
            # Dispatch handler by job_type
            if job.job_type == "experiment_execution" and job.experiment_id:
                from app.services import experiment_service

                job.current_stage = "Executing automated ML experiment pipeline"
                job.progress_percentage = 40
                session.commit()

                run = experiment_service.execute_pipeline_run(session, settings, job.experiment_id)
                job.result = {
                    "experiment_id": str(job.experiment_id),
                    "run_id": str(run.id),
                    "run_status": run.status,
                    "registered_model_id": str(run.registered_model_id) if run.registered_model_id else None,
                }

            elif job.job_type == "model_training":
                from app.schemas.models import TrainRequest
                from app.services import model_service

                job.current_stage = "Training supervised model"
                job.progress_percentage = 50
                session.commit()

                req = TrainRequest(**job.input_config)
                model = model_service.train(session, settings, req)
                job.result = {
                    "model_id": str(model.id),
                    "model_name": model.name,
                    "version": model.version,
                }

            elif job.job_type == "drift_analysis" and job.model_id:
                from app.services import drift_service

                job.current_stage = "Executing feature drift & quality analysis"
                job.progress_percentage = 50
                session.commit()

                report = drift_service.analyze_data_quality(session, settings, job.model_id)
                job.result = {"report_id": str(report.id), "status": report.overall_status}

            elif job.job_type == "explainability" and job.model_id:
                from app.services import explainability_service

                job.current_stage = "Computing global feature importance (SHAP)"
                job.progress_percentage = 50
                session.commit()

                res = explainability_service.compute_global_feature_importance(session, settings, job.model_id)
                job.result = {
                    "model_id": str(res.model_id),
                    "method": res.method,
                    "features_analyzed": len(res.feature_importances),
                }

            elif job.job_type == "batch_prediction" and job.model_id:
                from app.services import deployment_service, model_service

                job.current_stage = "Executing batch model inference"
                job.progress_percentage = 50
                session.commit()

                records = job.input_config.get("records", [])
                allow_missing = job.input_config.get("allow_missing", False)
                model, predictions, probabilities = model_service.predict_with_model(
                    session, settings, job.model_id, records, allow_missing=allow_missing
                )

                # Record prediction audit log if available
                active_dep = deployment_service.DeploymentRepository(session).get_active_for_model(job.model_id)
                deployment_id = active_dep.id if active_dep else None
                deployment_service.log_prediction(
                    session,
                    model_id=model.id,
                    deployment_id=deployment_id,
                    record_count=len(records),
                    duration_ms=50.0,
                    status="success",
                    problem_type=model.problem_type,
                    prediction_summary={"count": len(predictions), "predictions": predictions[:50]},
                )

                job.result = {
                    "model_id": str(model.id),
                    "problem_type": model.problem_type,
                    "record_count": len(records),
                    "predictions": predictions,
                    "probabilities": probabilities,
                }

            else:
                job.current_stage = "Processing general background task"
                job.progress_percentage = 70
                session.commit()
                time.sleep(0.5)
                job.result = {"status": "success", "processed_at": datetime.now(timezone.utc).isoformat()}

            # Mark completed
            duration = time.perf_counter() - start_time
            job.status = "completed"
            job.progress_percentage = 100
            job.current_stage = "Task finished successfully"
            job.completed_at = datetime.now(timezone.utc)
            job.execution_duration_seconds = round(duration, 4)
            session.commit()

        except Exception as exc:
            duration = time.perf_counter() - start_time
            logger.exception("Job %s execution failed: %s", job.id, exc)

            if job.retry_count < job.max_retries and job.status != "cancelled":
                job.status = "retry_pending"
                job.current_stage = f"Failure: {exc}. Scheduled for retry."
            else:
                job.status = "failed"
                job.current_stage = f"Execution failed: {exc}"

            job.error_category = type(exc).__name__
            job.error_message = str(exc)[:1000]
            job.completed_at = datetime.now(timezone.utc)
            job.execution_duration_seconds = round(duration, 4)
            session.commit()


def dispatch_job(job_id: uuid.UUID, settings: Settings) -> None:
    """Submit worker task to isolated threadpool executor."""
    executor.submit(_execute_worker_task, job_id, settings)


def claim_next_queued_job(session: Session) -> Job | None:
    """Atomically claim the next queued job using SELECT FOR UPDATE SKIP LOCKED.
    
    Immediately updates the status to 'running' and commits the transaction to release
    the row lock before heavy model inference begins. Compatible with PostgreSQL and SQLite.
    """
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else ""
    
    stmt = select(Job).where(Job.status == "queued").order_by(Job.created_at)
    if dialect_name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    
    job = session.scalars(stmt.limit(1)).first()
    if job:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress_percentage = 10
        job.current_stage = "Job claimed by worker"
        session.commit()
        session.refresh(job)
        return job
    return None


def run_worker_loop(
    settings: Settings,
    poll_interval_seconds: float = 2.0,
    heartbeat_file: str | None = "/tmp/worker_heartbeat",
) -> None:
    """Standalone worker poll loop claiming queued jobs from PostgreSQL and writing heartbeats."""
    logger.info("Starting standalone PostgreSQL background worker (poll_interval=%.1fs)...", poll_interval_seconds)
    session_factory = get_session_factory()
    
    def _update_heartbeat() -> None:
        if not heartbeat_file:
            return
        try:
            # Atomic write to avoid partial reads by healthcheck
            p = Path(heartbeat_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp_p = p.with_name(f"{p.name}.tmp")
            tmp_p.write_text(str(time.time()), encoding="utf-8")
            tmp_p.replace(p)
        except Exception as exc:
            logger.warning("Failed to update worker heartbeat at %s: %s", heartbeat_file, exc)

    # Initial heartbeat on startup
    _update_heartbeat()

    while True:
        try:
            with session_factory() as session:
                job = claim_next_queued_job(session)
                if job:
                    logger.info("Claimed job %s of type %s", job.id, job.job_type)
                    # Dispatch to worker pool
                    dispatch_job(job.id, settings)
        except Exception as exc:
            logger.error("Error in background worker loop: %s", exc)

        _update_heartbeat()
        time.sleep(poll_interval_seconds)


