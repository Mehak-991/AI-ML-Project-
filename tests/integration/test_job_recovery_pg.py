"""PostgreSQL concurrency tests for job claiming and stalled-job recovery (Phase 20).

REQUIRES a real, **disposable** PostgreSQL database migrated to head:
    TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/aiproject_test \
        pytest tests/integration/test_job_recovery_pg.py

Concurrency needs committed rows visible across connections, so these tests commit.
They only ever insert and delete their own jobs rows (tagged in input_config).
"""

import os
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.database.models import Base  # noqa: F401  (registers all mappers)
from app.database.models.job import Job
from app.services import job_service

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
requires_db = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def pg_factory():
    engine = create_engine(
        TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1), pool_size=10
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    tag = uuid.uuid4().hex
    yield factory, tag
    with factory() as session:
        session.execute(delete(Job).where(Job.input_config["test_tag"].as_string() == tag))
        session.commit()
    engine.dispose()


def _insert(factory, tag, n, **fields) -> list[uuid.UUID]:
    with factory() as session:
        jobs = [Job(job_type="batch_prediction", input_config={"test_tag": tag}, **fields) for _ in range(n)]
        session.add_all(jobs)
        session.commit()
        return [j.id for j in jobs]


def _stale_times(when: datetime) -> dict:
    return {"heartbeat_at": when, "started_at": when, "updated_at": when, "created_at": when}


def _run_concurrently(n_threads, target):
    barrier = threading.Barrier(n_threads)
    results, errors = [], []

    def runner():
        try:
            barrier.wait()
            results.append(target())
        except Exception as exc:  # surface thread failures in the test
            errors.append(exc)

    threads = [threading.Thread(target=runner) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert not errors, errors
    return results


@requires_db
def test_concurrent_reapers_recover_each_job_exactly_once(pg_factory) -> None:
    factory, tag = pg_factory
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    ids = _insert(factory, tag, 20, status="running", worker_id="dead:1", **_stale_times(stale))

    def reap():
        with factory() as session:
            return job_service.reap_stalled_jobs(session, 15)["recovered"]

    results = _run_concurrently(6, reap)
    counts = Counter(job_id for result in results for job_id in result if job_id in ids)
    assert set(counts) == set(ids)
    assert all(c == 1 for c in counts.values())
    with factory() as session:
        rows = session.scalars(select(Job).where(Job.id.in_(ids))).all()
    assert {r.status for r in rows} == {"retry_pending"}
    assert {r.retry_count for r in rows} == {0}


@requires_db
def test_reaper_skips_job_locked_by_finishing_worker(pg_factory) -> None:
    factory, tag = pg_factory
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    (job_id,) = _insert(factory, tag, 1, status="running", worker_id="slow:1", **_stale_times(stale))

    with factory() as worker_session:
        # The worker is writing its terminal state and holds the row lock.
        assert job_service._still_owns(worker_session, job_id, "slow:1")
        with factory() as reaper_session:
            outcome = job_service.reap_stalled_jobs(reaper_session, 15)
        assert job_id not in outcome["recovered"]
        job = worker_session.get(Job, job_id)
        job.status = "completed"
        worker_session.commit()

    with factory() as session:
        assert session.get(Job, job_id).status == "completed"
        assert job_id not in job_service.reap_stalled_jobs(session, 15)["recovered"]


@requires_db
def test_concurrent_workers_claim_each_job_exactly_once(pg_factory) -> None:
    factory, tag = pg_factory
    ids = set(_insert(factory, tag, 30, status="queued"))

    def drain():
        claimed = []
        while True:
            with factory() as session:
                job = job_service.claim_next_queued_job(session, f"w:{threading.get_ident()}")
            if job is None:
                return claimed
            if job.id in ids:
                claimed.append(job.id)

    results = _run_concurrently(5, drain)
    counts = Counter(job_id for result in results for job_id in result)
    assert set(counts) == ids
    assert all(c == 1 for c in counts.values())


@requires_db
def test_only_one_process_wins_execution_claim(pg_factory) -> None:
    factory, tag = pg_factory
    (job_id,) = _insert(factory, tag, 1, status="queued")
    names = iter(f"proc:{i}" for i in range(8))
    lock = threading.Lock()

    def claim():
        with lock:
            me = next(names)
        with factory() as session:
            return job_service._claim_for_execution(session, job_id, me)

    results = _run_concurrently(8, claim)
    assert results.count(True) == 1
