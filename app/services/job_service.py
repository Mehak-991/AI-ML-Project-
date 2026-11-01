"""Background job management, task queuing, execution dispatch, and lifecycle handling."""

import logging
import os
import socket
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import case, desc, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import DataValidationError, NotFoundError, PermissionDeniedError
from app.database.models.experiment import Experiment
from app.database.models.job import Job
from app.database.models.ml_model import MLModel
from app.database.models.user import User
from app.database.session import get_session_factory
from app.schemas.job import JobMetricsResponse
from app.services import authorization

logger = logging.getLogger(__name__)

# Dedicated background worker pool isolated from FastAPI's event loop
WORKER_THREADS = 3
executor = ThreadPoolExecutor(max_workers=WORKER_THREADS, thread_name_prefix="ml_worker_")

# A job in one of these states may be picked up for execution.
CLAIMABLE_STATUSES = ("queued", "retry_pending")


def worker_identity() -> str:
    """Identity of this process; computed per call so forked workers differ."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; PostgreSQL returns aware ones.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_postgres(session: Session) -> bool:
    bind = session.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


def create_job(
    session: Session,
    job_type: str,
    user: User,
    input_config: dict[str, Any],
    model_id: uuid.UUID | None = None,
    experiment_id: uuid.UUID | None = None,
    max_retries: int = 3,
) -> Job:
    # Validate linked entities exist and the caller may use the model
    if model_id:
        model = session.get(MLModel, model_id)
        if not model:
            raise NotFoundError(f"Model {model_id} not found.")
        authorization.ensure_model_access(user, model)
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

    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = session.scalars(stmt.offset(offset).limit(limit)).all()
    return list(items), total


def get_job_metrics(session: Session, user: User) -> JobMetricsResponse:
    # Aggregate in the database instead of loading every job row.
    stmt = select(Job.status, func.count()).group_by(Job.status)
    if user.role != "admin":
        stmt = stmt.where(Job.created_by_id == user.id)

    counts = dict(session.execute(stmt).all())
    return JobMetricsResponse(
        total_jobs=sum(counts.values()),
        queued_jobs=counts.get("queued", 0),
        running_jobs=counts.get("running", 0),
        completed_jobs=counts.get("completed", 0),
        failed_jobs=counts.get("failed", 0),
        cancelled_jobs=counts.get("cancelled", 0),
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


def _claim_for_execution(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Atomically take ownership of a job; True if this process may execute it.

    A conditional UPDATE means exactly one contender wins, whether the job was
    dispatched in-process by the API or claimed by a standalone worker. A job this
    process already claimed (claim_next_queued_job) is accepted when the lease matches.
    """
    now = _utcnow()
    result = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status.in_(CLAIMABLE_STATUSES))
        .values(
            status="running",
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Job.started_at, now),
            retry_count=case(
                (Job.status == "retry_pending", Job.retry_count + 1), else_=Job.retry_count
            ),
        )
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if result.rowcount == 1:
        return True
    row = session.execute(select(Job.status, Job.worker_id).where(Job.id == job_id)).one_or_none()
    return row is not None and row.status == "running" and row.worker_id == worker_id


def _still_owns(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Re-check the lease under a row lock before writing a terminal state.

    The lock is held until the caller commits, so the reaper (which uses SKIP
    LOCKED) cannot re-queue the job between this check and the write. A job that
    was cancelled or recovered meanwhile is left as it is.
    """
    with session.no_autoflush:
        row = session.execute(
            select(Job.status, Job.worker_id).where(Job.id == job_id).with_for_update()
        ).one_or_none()
    return row is not None and row.status == "running" and row.worker_id == worker_id


class _JobHeartbeat:
    """Refreshes jobs.heartbeat_at from its own session while a job executes."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        job_id: uuid.UUID,
        worker_id: str,
        interval_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._job_id = job_id
        self._worker_id = worker_id
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name=f"job-heartbeat-{job_id}", daemon=True
        )

    def __enter__(self) -> "_JobHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def beat(self) -> None:
        with self._session_factory() as session:
            session.execute(
                update(Job)
                .where(
                    Job.id == self._job_id,
                    Job.worker_id == self._worker_id,
                    Job.status == "running",
                )
                .values(heartbeat_at=_utcnow())
                .execution_options(synchronize_session=False)
            )
            session.commit()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.beat()
            except Exception as exc:  # a heartbeat failure must never kill the job
                logger.warning(
                    "Heartbeat failed for job %s: %s",
                    self._job_id,
                    exc,
                    extra={"job_id": str(self._job_id), "worker_id": self._worker_id},
                )


def _execute_worker_task(job_id: uuid.UUID, settings: Settings) -> None:
    """Asynchronous worker executing job processing in dedicated thread."""
    session_factory = get_session_factory()
    worker_id = worker_identity()
    with session_factory() as session:
        if not _claim_for_execution(session, job_id, worker_id):
            logger.info(
                "Skipping job %s: claimed by another worker or no longer runnable",
                job_id,
                extra={"job_id": str(job_id), "worker_id": worker_id},
            )
            return
        job = session.get(Job, job_id, populate_existing=True)
        if job is None:
            return
        heartbeat = _JobHeartbeat(
            session_factory, job.id, worker_id, settings.JOB_HEARTBEAT_INTERVAL_SECONDS
        )
        with heartbeat:
            _run_claimed_job(session, settings, job, worker_id)


def _run_claimed_job(session: Session, settings: Settings, job: Job, worker_id: str) -> None:
    log_context = {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "model_id": str(job.model_id) if job.model_id else None,
        "worker_id": worker_id,
    }

    job.progress_percentage = 15
    job.current_stage = "Initializing worker pipeline"
    session.commit()

    start_time = time.perf_counter()
    logger.info(
        "Starting execution for job %s [type=%s, model_id=%s]",
        job.id,
        job.job_type,
        job.model_id,
        extra=log_context,
    )

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
            model = model_service.train(session, settings, req, owner_id=job.created_by_id)
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
            _infer_start = time.perf_counter()
            model, predictions, probabilities = model_service.predict_with_model(
                session, settings, job.model_id, records, allow_missing=allow_missing
            )
            _infer_duration_ms = (time.perf_counter() - _infer_start) * 1000.0

            # Record prediction audit log if available
            active_dep = deployment_service.DeploymentRepository(session).get_active_for_model(job.model_id)
            deployment_id = active_dep.id if active_dep else None
            deployment_service.log_prediction(
                session,
                model_id=model.id,
                deployment_id=deployment_id,
                record_count=len(records),
                duration_ms=_infer_duration_ms,
                status="success",
                problem_type=model.problem_type,
                prediction_summary={"count": len(predictions), "predictions": predictions[:50]},
                requested_by_id=job.created_by_id,
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

        # Mark completed, unless the job was cancelled or recovered meanwhile
        duration = time.perf_counter() - start_time
        if not _still_owns(session, job.id, worker_id):
            session.rollback()
            logger.warning(
                "Discarding result of job %s: lease lost (cancelled or recovered) during execution",
                job.id,
                extra={**log_context, "duration_seconds": round(duration, 4)},
            )
            return
        job.status = "completed"
        job.progress_percentage = 100
        job.current_stage = "Task finished successfully"
        job.completed_at = datetime.now(timezone.utc)
        job.execution_duration_seconds = round(duration, 4)
        job.worker_id = None
        session.commit()

        logger.info(
            "Completed job %s [type=%s, model_id=%s] in %.4fs",
            job.id,
            job.job_type,
            job.model_id,
            duration,
            extra={**log_context, "duration_seconds": round(duration, 4)},
        )

    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.exception(
            "Job %s [type=%s, model_id=%s] execution failed: %s",
            job.id,
            job.job_type,
            job.model_id,
            exc,
            extra={**log_context, "error": str(exc), "duration_seconds": round(duration, 4)},
        )

        session.rollback()  # drop partial handler state before recording the failure
        if not _still_owns(session, job.id, worker_id):
            session.rollback()
            logger.warning(
                "Not recording failure of job %s: lease lost during execution",
                job.id,
                extra=log_context,
            )
            return

        # Validation and missing entity errors are permanent; do not retry them blindly
        is_permanent_error = isinstance(exc, (DataValidationError, NotFoundError))
        if not is_permanent_error and job.retry_count < job.max_retries:
            job.status = "retry_pending"
            job.current_stage = f"Failure: {exc}. Scheduled for retry."
        else:
            job.status = "failed"
            job.current_stage = f"Execution failed: {exc}"

        job.error_category = type(exc).__name__
        job.error_message = str(exc)[:1000]
        job.completed_at = datetime.now(timezone.utc)
        job.execution_duration_seconds = round(duration, 4)
        job.worker_id = None
        session.commit()


def dispatch_job(job_id: uuid.UUID, settings: Settings) -> Future:
    """Submit worker task to isolated threadpool executor."""
    return executor.submit(_execute_worker_task, job_id, settings)


def claim_next_queued_job(session: Session, worker_id: str | None = None) -> Job | None:
    """Atomically claim the next queued (or retry-pending) job using SELECT FOR UPDATE SKIP LOCKED.

    Immediately updates the status to 'running' and commits the transaction to release
    the row lock before heavy model inference begins. Compatible with PostgreSQL and SQLite.
    Picking up a retry_pending job counts as one retry.
    """
    stmt = select(Job).where(Job.status.in_(CLAIMABLE_STATUSES)).order_by(Job.created_at)
    if _is_postgres(session):
        stmt = stmt.with_for_update(skip_locked=True)

    job = session.scalars(stmt.limit(1)).first()
    if job:
        now = _utcnow()
        if job.status == "retry_pending":
            job.retry_count += 1
        job.status = "running"
        job.worker_id = worker_id or worker_identity()
        job.heartbeat_at = now
        job.started_at = now
        job.progress_percentage = 10
        job.current_stage = "Job claimed by worker"
        session.commit()
        session.refresh(job)
        return job
    return None


def _last_alive(job: Job) -> datetime:
    """Most recent liveness signal; rows from before heartbeats fall back to timestamps."""
    candidates = [job.heartbeat_at, job.updated_at, job.started_at, job.created_at]
    return max(_as_aware(c) for c in candidates if c is not None)


def reap_stalled_jobs(
    session: Session,
    timeout_minutes: int,
    *,
    timeout_by_type: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, list[uuid.UUID]]:
    """Recover jobs left 'running' by a worker that stopped heartbeating.

    A job is stale only when its most recent liveness signal (heartbeat, else last
    update) is older than its timeout, so long-running jobs whose worker is alive are
    untouched. Stale jobs with retries left move to 'retry_pending' (retry_count is
    incremented when they are claimed again); exhausted ones are marked 'failed'.
    Terminal jobs are never selected, so failed/completed/cancelled jobs are not
    resurrected.

    On PostgreSQL rows are locked with FOR UPDATE SKIP LOCKED: concurrent reapers never
    process the same job, and a worker writing its final state (which holds the row
    lock) is skipped. Running it again is a no-op, i.e. recovery is idempotent.
    """
    now = now or _utcnow()
    overrides = timeout_by_type or {}
    stmt = select(Job).where(Job.status == "running").order_by(Job.created_at)
    if _is_postgres(session):
        stmt = stmt.with_for_update(skip_locked=True)

    recovered: list[uuid.UUID] = []
    failed: list[uuid.UUID] = []
    for job in session.scalars(stmt).all():
        timeout = timedelta(minutes=overrides.get(job.job_type, timeout_minutes))
        last_alive = _last_alive(job)
        if now - last_alive < timeout:
            continue

        log_extra = {
            "job_id": str(job.id),
            "job_type": job.job_type,
            "model_id": str(job.model_id) if job.model_id else None,
            "stale_worker_id": job.worker_id,
            "last_heartbeat": last_alive.isoformat(),
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
        }
        job.worker_id = None
        job.heartbeat_at = None
        if job.retry_count < job.max_retries:
            job.status = "retry_pending"
            job.current_stage = "Recovered from stalled worker; scheduled for retry"
            recovered.append(job.id)
            logger.warning("Recovered stalled job %s for retry", job.id, extra=log_extra)
        else:
            job.status = "failed"
            job.current_stage = "Execution failed: worker stalled and retries exhausted"
            job.error_category = "WorkerStalled"
            job.error_message = (
                f"No heartbeat since {last_alive.isoformat()}; retries exhausted "
                f"({job.retry_count}/{job.max_retries})."
            )
            job.completed_at = now
            failed.append(job.id)
            logger.error("Failed stalled job %s: retries exhausted", job.id, extra=log_extra)
    session.commit()
    return {"recovered": recovered, "failed": failed}


def run_worker_loop(
    settings: Settings,
    poll_interval_seconds: float = 2.0,
    heartbeat_file: str | None = "/tmp/worker_heartbeat",
    max_iterations: int | None = None,
) -> None:
    """Standalone worker poll loop claiming queued jobs from PostgreSQL and writing heartbeats.

    Stalled jobs are reaped at startup and then every JOB_REAPER_INTERVAL_SECONDS.
    A job is claimed only when a pool thread is free, so claimed jobs never wait
    (without heartbeats) in the executor queue.
    """
    logger.info("Starting standalone PostgreSQL background worker (poll_interval=%.1fs)...", poll_interval_seconds)
    session_factory = get_session_factory()
    worker_id = worker_identity()
    in_flight: set[Future] = set()

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

    def _reap() -> None:
        try:
            with session_factory() as session:
                outcome = reap_stalled_jobs(
                    session,
                    settings.JOB_STALE_TIMEOUT_MINUTES,
                    timeout_by_type=settings.JOB_STALE_TIMEOUT_BY_TYPE,
                )
            if outcome["recovered"] or outcome["failed"]:
                logger.warning(
                    "Stalled-job recovery: %d re-queued, %d failed",
                    len(outcome["recovered"]),
                    len(outcome["failed"]),
                    extra={
                        "worker_id": worker_id,
                        "recovered_job_ids": [str(i) for i in outcome["recovered"]],
                        "failed_job_ids": [str(i) for i in outcome["failed"]],
                    },
                )
        except Exception as exc:
            logger.error("Stalled-job recovery failed: %s", exc, extra={"worker_id": worker_id})

    # Initial heartbeat and recovery on startup
    _update_heartbeat()
    _reap()
    last_reap = time.monotonic()

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        if time.monotonic() - last_reap >= settings.JOB_REAPER_INTERVAL_SECONDS:
            _reap()
            last_reap = time.monotonic()

        in_flight = {f for f in in_flight if not f.done()}
        if len(in_flight) < WORKER_THREADS:
            try:
                with session_factory() as session:
                    job = claim_next_queued_job(session, worker_id)
                    if job:
                        logger.info(
                            "Claimed job %s of type %s",
                            job.id,
                            job.job_type,
                            extra={
                                "job_id": str(job.id),
                                "job_type": job.job_type,
                                "model_id": str(job.model_id) if job.model_id else None,
                                "worker_id": worker_id,
                            },
                        )
                        # Dispatch to worker pool
                        in_flight.add(dispatch_job(job.id, settings))
            except Exception as exc:
                logger.error("Error in background worker loop: %s", exc)

        _update_heartbeat()
        time.sleep(poll_interval_seconds)
