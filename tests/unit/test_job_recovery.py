"""Phase 20: stalled-job recovery, job leases and duplicate-execution protection.

SQLite cannot show row-lock concurrency; the PostgreSQL concurrency cases live in
tests/integration/test_job_recovery_pg.py.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.database.models.job import Job
from app.services import job_service

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


def _job(session, *, status="running", age_minutes=0, heartbeat_minutes=None, **fields) -> Job:
    started = NOW - timedelta(minutes=age_minutes)
    job = Job(
        job_type=fields.pop("job_type", "batch_prediction"),
        status=status,
        input_config={},
        started_at=started,
        created_at=started,
        updated_at=started,
        heartbeat_at=None if heartbeat_minutes is None else NOW - timedelta(minutes=heartbeat_minutes),
        worker_id=fields.pop("worker_id", "dead-host:1" if status == "running" else None),
        **fields,
    )
    session.add(job)
    session.commit()
    return job


def _reload(session_factory, job_id) -> Job:
    with session_factory() as s:
        return s.get(Job, job_id)


def test_stale_running_job_is_recovered_for_retry(db_session, session_factory, caplog) -> None:
    job = _job(db_session, age_minutes=30, heartbeat_minutes=20, retry_count=0, max_retries=3)
    with caplog.at_level(logging.WARNING, logger="app.services.job_service"):
        outcome = job_service.reap_stalled_jobs(db_session, 15, now=NOW)
    assert outcome == {"recovered": [job.id], "failed": []}
    job = _reload(session_factory, job.id)
    assert job.status == "retry_pending"
    assert job.worker_id is None and job.heartbeat_at is None
    assert job.retry_count == 0  # counted when the retry is actually claimed
    record = next(r for r in caplog.records if "Recovered stalled job" in r.getMessage())
    assert record.job_id == str(job.id) and record.stale_worker_id == "dead-host:1"


def test_recent_heartbeat_keeps_long_running_job_untouched(db_session, session_factory) -> None:
    # Started two hours ago but the worker heartbeated a minute ago: still alive.
    job = _job(db_session, age_minutes=120, heartbeat_minutes=1)
    assert job_service.reap_stalled_jobs(db_session, 15, now=NOW) == {"recovered": [], "failed": []}
    reloaded = _reload(session_factory, job.id)
    assert reloaded.status == "running" and reloaded.worker_id == "dead-host:1"


def test_legacy_running_job_without_heartbeat_uses_last_update(db_session, session_factory) -> None:
    fresh = _job(db_session, age_minutes=5)  # no heartbeat column value (pre-Phase 20 row)
    stale = _job(db_session, age_minutes=60)
    outcome = job_service.reap_stalled_jobs(db_session, 15, now=NOW)
    assert outcome["recovered"] == [stale.id]
    assert _reload(session_factory, fresh.id).status == "running"


def test_retry_limit_exhausted_marks_failed(db_session, session_factory) -> None:
    job = _job(db_session, age_minutes=60, heartbeat_minutes=40, retry_count=2, max_retries=2)
    outcome = job_service.reap_stalled_jobs(db_session, 15, now=NOW)
    assert outcome == {"recovered": [], "failed": [job.id]}
    job = _reload(session_factory, job.id)
    assert job.status == "failed"
    assert job.error_category == "WorkerStalled"
    assert job.completed_at is not None


@pytest.mark.parametrize("status", ["failed", "completed", "cancelled", "queued", "retry_pending"])
def test_non_running_jobs_are_never_touched(db_session, session_factory, status) -> None:
    job = _job(db_session, status=status, age_minutes=600)
    assert job_service.reap_stalled_jobs(db_session, 15, now=NOW) == {"recovered": [], "failed": []}
    assert _reload(session_factory, job.id).status == status


def test_recovery_is_idempotent(db_session) -> None:
    _job(db_session, age_minutes=60, heartbeat_minutes=60)
    first = job_service.reap_stalled_jobs(db_session, 15, now=NOW)
    second = job_service.reap_stalled_jobs(db_session, 15, now=NOW)
    assert len(first["recovered"]) == 1
    assert second == {"recovered": [], "failed": []}


def test_per_job_type_timeout_override(db_session) -> None:
    training = _job(db_session, job_type="model_training", age_minutes=40, heartbeat_minutes=40)
    batch = _job(db_session, job_type="batch_prediction", age_minutes=40, heartbeat_minutes=40)
    outcome = job_service.reap_stalled_jobs(
        db_session, 15, timeout_by_type={"model_training": 60}, now=NOW
    )
    assert outcome["recovered"] == [batch.id]
    assert training.id not in outcome["recovered"]


def test_claim_sets_lease_and_counts_retries(db_session) -> None:
    retry = _job(db_session, status="retry_pending", age_minutes=10, retry_count=1)
    claimed = job_service.claim_next_queued_job(db_session, "worker-a:1")
    assert claimed.id == retry.id
    assert claimed.status == "running"
    assert claimed.worker_id == "worker-a:1"
    assert claimed.heartbeat_at is not None
    assert claimed.retry_count == 2
    assert job_service.claim_next_queued_job(db_session, "worker-b:1") is None


def test_claim_keeps_fifo_order_over_queued_jobs(db_session) -> None:
    older = _job(db_session, status="queued", age_minutes=10)
    _job(db_session, status="queued", age_minutes=5)
    assert job_service.claim_next_queued_job(db_session, "w:1").id == older.id


# --- execution: duplicate protection and fenced completion -----------------------------


@pytest.fixture
def worker_env(monkeypatch, session_factory, make_settings):
    """Run _execute_worker_task synchronously against the SQLite test database."""
    monkeypatch.setattr(job_service, "get_session_factory", lambda: session_factory)
    monkeypatch.setattr(job_service, "worker_identity", lambda: "this-host:42")
    calls: list[uuid.UUID] = []

    def fake_predict(session, settings, model_id, records, *, allow_missing):
        calls.append(model_id)
        model = type("M", (), {"id": model_id, "problem_type": "classification"})()
        return model, [1] * len(records), None

    from app.services import deployment_service, model_service

    monkeypatch.setattr(model_service, "predict_with_model", fake_predict)
    monkeypatch.setattr(deployment_service, "log_prediction", lambda *a, **k: None)
    monkeypatch.setattr(
        deployment_service.DeploymentRepository, "get_active_for_model", lambda self, mid: None
    )
    return {"settings": make_settings(), "predict_calls": calls}


def _with_model(session, job: Job) -> Job:
    job.model_id = uuid.uuid4()
    job.input_config = {"records": [{"a": 1}]}
    session.commit()
    return job


def test_queued_job_executes_once_and_releases_lease(db_session, session_factory, worker_env) -> None:
    job = _with_model(db_session, _job(db_session, status="queued"))
    job_service._execute_worker_task(job.id, worker_env["settings"])
    job_service._execute_worker_task(job.id, worker_env["settings"])  # duplicate dispatch
    assert len(worker_env["predict_calls"]) == 1
    done = _reload(session_factory, job.id)
    assert done.status == "completed" and done.worker_id is None
    assert done.result["record_count"] == 1


def test_job_claimed_by_another_worker_is_not_executed(db_session, session_factory, worker_env) -> None:
    job = _with_model(
        db_session, _job(db_session, status="running", worker_id="other-host:7", heartbeat_minutes=0)
    )
    job_service._execute_worker_task(job.id, worker_env["settings"])
    assert worker_env["predict_calls"] == []
    assert _reload(session_factory, job.id).worker_id == "other-host:7"


def test_worker_restart_does_not_duplicate_live_prediction(
    db_session, session_factory, worker_env, tmp_path
) -> None:
    """A newly started worker must neither reap nor re-run a job another live worker owns."""
    job = _with_model(
        db_session,
        _job(db_session, status="running", worker_id="old-host:1", age_minutes=0, heartbeat_minutes=0),
    )
    job.heartbeat_at = datetime.now(timezone.utc)
    db_session.commit()
    job_service.run_worker_loop(
        worker_env["settings"],
        poll_interval_seconds=0,
        heartbeat_file=str(tmp_path / "hb"),
        max_iterations=1,
    )
    job_service.executor.submit(lambda: None).result()  # drain anything dispatched
    assert worker_env["predict_calls"] == []
    reloaded = _reload(session_factory, job.id)
    assert reloaded.status == "running" and reloaded.worker_id == "old-host:1"


def test_worker_startup_recovers_abandoned_job_then_runs_it_once(
    db_session, session_factory, worker_env, tmp_path
) -> None:
    job = _job(db_session, status="running", worker_id="crashed:1", age_minutes=60, heartbeat_minutes=60)
    job = _with_model(db_session, job)
    # Move the abandoned job's timestamps into the real past relative to wall-clock time.
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    job.heartbeat_at = job.updated_at = job.started_at = old
    db_session.commit()
    with session_factory() as s:  # updated_at has onupdate=now(); force it back
        s.query(Job).filter(Job.id == job.id).update(
            {"updated_at": old, "heartbeat_at": old}, synchronize_session=False
        )
        s.commit()

    job_service.run_worker_loop(
        worker_env["settings"], poll_interval_seconds=0, heartbeat_file=str(tmp_path / "hb"), max_iterations=1
    )
    job_service.executor.submit(lambda: None).result()
    for _ in range(50):  # the dispatched task runs on the pool; wait for completion
        if _reload(session_factory, job.id).status == "completed":
            break
        time.sleep(0.05)
    done = _reload(session_factory, job.id)
    assert done.status == "completed"
    assert done.retry_count == 1
    assert len(worker_env["predict_calls"]) == 1


def test_cancellation_during_execution_is_not_overwritten(
    db_session, session_factory, worker_env, monkeypatch
) -> None:
    job = _with_model(db_session, _job(db_session, status="queued"))
    from app.services import model_service

    original = model_service.predict_with_model

    def cancel_midway(session, settings, model_id, records, *, allow_missing):
        with session_factory() as other:
            other.get(Job, job.id).status = "cancelled"
            other.commit()
        return original(session, settings, model_id, records, allow_missing=allow_missing)

    monkeypatch.setattr(model_service, "predict_with_model", cancel_midway)
    job_service._execute_worker_task(job.id, worker_env["settings"])
    assert _reload(session_factory, job.id).status == "cancelled"


def test_result_discarded_when_lease_lost_to_recovery(
    db_session, session_factory, worker_env, monkeypatch
) -> None:
    job = _with_model(db_session, _job(db_session, status="queued"))
    from app.services import model_service

    original = model_service.predict_with_model

    def reaped_midway(session, settings, model_id, records, *, allow_missing):
        with session_factory() as other:  # simulate the reaper re-queuing the job
            j = other.get(Job, job.id)
            j.status, j.worker_id = "retry_pending", None
            other.commit()
        return original(session, settings, model_id, records, allow_missing=allow_missing)

    monkeypatch.setattr(model_service, "predict_with_model", reaped_midway)
    job_service._execute_worker_task(job.id, worker_env["settings"])
    reloaded = _reload(session_factory, job.id)
    assert reloaded.status == "retry_pending"
    assert reloaded.result is None


def test_failure_schedules_retry_and_retry_counts(db_session, session_factory, worker_env, monkeypatch) -> None:
    job = _with_model(db_session, _job(db_session, status="queued", max_retries=1))
    from app.services import model_service

    def boom(*args, **kwargs):
        raise RuntimeError("transient")

    monkeypatch.setattr(model_service, "predict_with_model", boom)
    job_service._execute_worker_task(job.id, worker_env["settings"])
    first = _reload(session_factory, job.id)
    assert first.status == "retry_pending" and first.retry_count == 0 and first.worker_id is None

    job_service._execute_worker_task(job.id, worker_env["settings"])  # the retry
    second = _reload(session_factory, job.id)
    assert second.retry_count == 1
    assert second.status == "failed"  # retries exhausted: no infinite retry loop


def test_heartbeat_only_updates_owned_running_job(db_session, session_factory) -> None:
    mine = _job(db_session, status="running", worker_id="me:1", heartbeat_minutes=10)
    theirs = _job(db_session, status="running", worker_id="them:1", heartbeat_minutes=10)
    before = _reload(session_factory, theirs.id).heartbeat_at
    job_service._JobHeartbeat(session_factory, mine.id, "me:1", 30).beat()
    job_service._JobHeartbeat(session_factory, theirs.id, "me:1", 30).beat()
    refreshed = job_service._as_aware(_reload(session_factory, mine.id).heartbeat_at)
    assert refreshed > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _reload(session_factory, theirs.id).heartbeat_at == before


def test_job_timeout_settings_validated() -> None:
    Settings(_env_file=None, JOB_STALE_TIMEOUT_MINUTES=2, JOB_HEARTBEAT_INTERVAL_SECONDS=30)
    with pytest.raises(ValueError):
        Settings(_env_file=None, JOB_STALE_TIMEOUT_MINUTES=1, JOB_HEARTBEAT_INTERVAL_SECONDS=30)
    with pytest.raises(ValueError):
        Settings(_env_file=None, JOB_STALE_TIMEOUT_BY_TYPE={"x": 1}, JOB_HEARTBEAT_INTERVAL_SECONDS=30)


def test_job_list_total_and_metrics_are_aggregated_in_sql(db_session) -> None:
    from app.database.models.user import User

    owner = User(email="o@x.com", hashed_password="x", role="ml_engineer")
    other = User(email="p@x.com", hashed_password="x", role="ml_engineer")
    admin = User(email="a@x.com", hashed_password="x", role="admin")
    db_session.add_all([owner, other, admin])
    db_session.commit()
    for status in ["queued", "queued", "running", "completed", "failed", "cancelled", "retry_pending"]:
        _job(db_session, status=status, created_by_id=owner.id)
    _job(db_session, status="completed", created_by_id=other.id)

    items, total = job_service.list_jobs(db_session, owner, offset=2, limit=3)
    assert total == 7 and len(items) == 3
    assert job_service.list_jobs(db_session, admin, limit=1)[1] == 8
    assert job_service.list_jobs(db_session, owner, status="queued")[1] == 2

    metrics = job_service.get_job_metrics(db_session, owner)
    assert (metrics.total_jobs, metrics.queued_jobs, metrics.running_jobs) == (7, 2, 1)
    assert (metrics.completed_jobs, metrics.failed_jobs, metrics.cancelled_jobs) == (1, 1, 1)
    assert job_service.get_job_metrics(db_session, admin).completed_jobs == 2
