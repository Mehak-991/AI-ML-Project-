"""RBAC v2 on real PostgreSQL: concurrency, the append-only audit triggers, and migration 0014.

REQUIRES a disposable database via TEST_DATABASE_URL (see test_database.py). Concurrency tests run
in a throwaway schema; the migration tests create and drop a scratch database. The role used must
be allowed to CREATE DATABASE (a superuser, as in CI and in the Docker test database).
"""

import argparse
import threading
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, ConflictError
from app.database.models.audit import AuditLog
from app.database.models.user import User
from app.schemas.auth import UserRegisterRequest, UserUpdateRequest
from app.services import auth_service
from tests.integration.test_database import TEST_DATABASE_URL, pg_isolated_engine, requires_db  # noqa: F401

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Str0ngPassw0rd"
SETTINGS = Settings(_env_file=None, APP_ENV="testing")


def _make_superadmins(factory, count: int, prefix: str = "su") -> list[User]:
    from app.core import security

    users = []
    with factory() as session:
        hashed = security.hash_password(PASSWORD)
        for index in range(count):
            user = User(email=f"{prefix}{index}@x.com", hashed_password=hashed, full_name="", role="superadmin", is_active=True)
            session.add(user)
            users.append(user)
        session.commit()
        for user in users:
            session.refresh(user)
            session.expunge(user)
    return users


def _active_superadmins(factory, prefix: str | None = None) -> int:
    with factory() as session:
        stmt = select(func.count()).select_from(User).where(User.role == "superadmin", User.is_active.is_(True))
        if prefix:
            stmt = stmt.where(User.email.like(f"{prefix}%"))
        return session.scalar(stmt)


def _race(jobs: list) -> list:
    """Run callables on separate threads, released together; return each outcome or exception."""
    barrier = threading.Barrier(len(jobs))
    outcomes: list = [None] * len(jobs)

    def run(index, job):
        barrier.wait()
        try:
            outcomes[index] = job()
        except Exception as exc:
            outcomes[index] = exc

    threads = [threading.Thread(target=run, args=(i, job)) for i, job in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert all(o is not None for o in outcomes), "a worker thread did not finish"
    return outcomes


# --- the last-superadmin guard under real concurrency ------------------------------------------


@requires_db
def test_two_superadmins_demoting_each_other_at_once_leave_exactly_one(pg_isolated_engine) -> None:  # noqa: F811
    """Repeated over many fresh pairs: a single round rarely opens the race window on a fast
    machine, so one round could pass even without the row lock."""
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)

    def revoke(actor, target):
        def job():
            with factory() as session:
                return auth_service.revoke_superadmin(session, actor, target.id)

        return job

    for round_number in range(25):
        prefix = f"r{round_number}x"
        # Each round starts from an empty users table. The guard (correctly) counts every active
        # superadmin, so survivors of earlier rounds would make later rounds legitimately safe.
        with factory() as session:
            session.execute(delete(User))
            session.commit()
        a, b = _make_superadmins(factory, 2, prefix)
        outcomes = _race([revoke(a, b), revoke(b, a)])
        wins = [o for o in outcomes if isinstance(o, User)]
        refused = [o for o in outcomes if isinstance(o, ConflictError)]
        assert len(wins) == 1 and len(refused) == 1, (round_number, outcomes)
        assert "last active superadmin" in refused[0].message
        assert _active_superadmins(factory, prefix) == 1, f"round {round_number} emptied the superadmin set"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "superadmin.revoked")) == 25


@requires_db
def test_a_ring_of_five_superadmins_can_never_all_be_removed(pg_isolated_engine) -> None:  # noqa: F811
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)
    users = _make_superadmins(factory, 5)

    def revoke(actor, target):
        def job():
            with factory() as session:
                return auth_service.revoke_superadmin(session, actor, target.id)

        return job

    outcomes = _race([revoke(users[i], users[(i + 1) % 5]) for i in range(5)])
    assert sum(isinstance(o, User) for o in outcomes) == 4, outcomes
    assert sum(isinstance(o, ConflictError) for o in outcomes) == 1, outcomes
    assert _active_superadmins(factory) == 1
    with factory() as session:  # one audit entry per successful change, none for the refused one
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 4


@requires_db
def test_concurrent_deactivations_and_demotions_cannot_empty_the_superadmin_set(pg_isolated_engine) -> None:  # noqa: F811
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)
    users = _make_superadmins(factory, 4)

    def deactivate(actor, target):
        def job():
            with factory() as session:
                return auth_service.update_user(session, actor, target.id, UserUpdateRequest(is_active=False), SETTINGS)

        return job

    def revoke(actor, target):
        def job():
            with factory() as session:
                return auth_service.revoke_superadmin(session, actor, target.id)

        return job

    jobs = []
    for i in range(4):
        target = users[(i + 1) % 4]
        jobs.append(deactivate(users[i], target) if i % 2 == 0 else revoke(users[i], target))
    outcomes = _race(jobs)
    assert not [o for o in outcomes if isinstance(o, Exception) and not isinstance(o, AppError)], outcomes
    assert _active_superadmins(factory) >= 1


@requires_db
def test_simultaneous_bootstrap_creates_exactly_one_superadmin(pg_isolated_engine) -> None:  # noqa: F811
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)

    def bootstrap(index):
        def job():
            with factory() as session:
                return auth_service.bootstrap_superadmin(session, email=f"boss{index}@x.com", password=PASSWORD)

        return job

    outcomes = _race([bootstrap(i) for i in range(8)])
    assert sum(isinstance(o, User) for o in outcomes) == 1, outcomes
    assert all(isinstance(o, (User, ConflictError)) for o in outcomes), outcomes
    assert _active_superadmins(factory) == 1


@requires_db
def test_concurrent_public_registrations_never_produce_a_privileged_account(pg_isolated_engine) -> None:  # noqa: F811
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)

    def register(index):
        def job():
            with factory() as session:
                return auth_service.register_user(
                    session, UserRegisterRequest(email=f"u{index}@x.com", password=PASSWORD), SETTINGS
                )

        return job

    outcomes = _race([register(i) for i in range(12)])
    assert all(isinstance(o, User) and o.role == "user" for o in outcomes), outcomes
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User).where(User.role != "user")) == 0


# --- migration 0014 on real PostgreSQL ---------------------------------------------------------


@pytest.fixture
def scratch_db(monkeypatch, tmp_path):
    """A brand-new database for one test: created before, dropped after."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    base = make_url(TEST_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))
    name = f"rbac_mig_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = create_engine(url)
    try:
        yield config, engine, tmp_path
    finally:
        engine.dispose()
        get_settings.cache_clear()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _seed(engine, roles: list[tuple[str, str]]) -> dict[str, uuid.UUID]:
    ids = {}
    with engine.begin() as conn:
        for email, role in roles:
            ids[email] = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                    "VALUES (:id, :email, :hash, '', :role, true)"
                ),
                {"id": ids[email], "email": email, "hash": f"hash-of-{email}", "role": role},
            )
        conn.execute(
            text(
                "INSERT INTO datasets (id, name, original_filename, stored_filename, file_format, size_bytes, sha256, "
                "n_rows, n_columns, columns, owner_id) VALUES (:id, 'd', 'd.csv', 's.csv', 'csv', 1, :sha, 1, 1, '[]'::jsonb, :o)"
            ),
            {"id": uuid.uuid4(), "sha": "0" * 64, "o": ids["admin@x.com"]},
        )
    return ids


@requires_db
def test_migration_on_postgres_maps_roles_preserves_data_and_installs_the_audit_triggers(scratch_db) -> None:
    config, engine, _ = scratch_db
    command.upgrade(config, "0013")
    ids = _seed(engine, [("viewer@x.com", "viewer"), ("admin@x.com", "admin"), ("ml@x.com", "ml_engineer")])
    with pytest.raises(RuntimeError, match="aborted"):
        command.upgrade(config, "0014")
    with engine.connect() as conn:  # PostgreSQL rolled the failed migration back completely
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0013"
        assert conn.execute(text("SELECT to_regclass('audit_logs')")).scalar() is None

    config.cmd_opts = argparse.Namespace(x=["ml_engineer=user"])
    command.upgrade(config, "0014")
    config.cmd_opts = None

    with engine.connect() as conn:
        roles = dict(conn.execute(text("SELECT email, role FROM users")).all())
        hashes = dict(conn.execute(text("SELECT email, hashed_password FROM users")).all())
        owner = conn.execute(text("SELECT owner_id FROM datasets")).scalar()
        audit = conn.execute(text("SELECT action, target_email, before, after FROM audit_logs")).all()
        default = conn.execute(
            text("SELECT column_default FROM information_schema.columns WHERE table_name='users' AND column_name='role'")
        ).scalar()
    assert roles == {"viewer@x.com": "user", "admin@x.com": "admin", "ml@x.com": "user"}
    assert hashes == {e: f"hash-of-{e}" for e in roles}
    assert owner == ids["admin@x.com"]
    assert audit == [("migration.role_mapped", "ml@x.com", {"role": "ml_engineer"}, {"role": "user"})]
    assert "user" in default

    # The audit trail is append-only at the database level.
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_logs (id, action) VALUES (:i, 'user.created')"), {"i": uuid.uuid4()})
    for statement in ("UPDATE audit_logs SET action = 'x'", "DELETE FROM audit_logs", "TRUNCATE audit_logs"):
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
            conn.execute(text(statement))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar() == 2

    # The CHECK constraint refuses retired and invented roles.
    for bad in ("ml_engineer", "root"):
        with pytest.raises(DBAPIError, match="ck_users_role"), engine.begin() as conn:
            conn.execute(
                text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) VALUES (:i, :e, 'h', '', :r, true)"),
                {"i": uuid.uuid4(), "e": f"{bad}@x.com", "r": bad},
            )


@requires_db
def test_migrated_postgres_schema_matches_the_models(scratch_db) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database.models import Base

    config, engine, _ = scratch_db
    command.upgrade(config, "head")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == [], diff


@requires_db
def test_postgres_downgrade_is_guarded_and_restores_the_legacy_roles(scratch_db) -> None:
    config, engine, tmp = scratch_db
    command.upgrade(config, "0014")
    with engine.begin() as conn:
        for email, role in (("u@x.com", "user"), ("a@x.com", "admin"), ("s@x.com", "superadmin")):
            conn.execute(
                text("INSERT INTO users (id, email, hashed_password, full_name, role, is_active) VALUES (:i, :e, 'h', '', :r, true)"),
                {"i": uuid.uuid4(), "e": email, "r": role},
            )
        conn.execute(text("INSERT INTO audit_logs (id, action) VALUES (:i, 'user.created')"), {"i": uuid.uuid4()})

    with pytest.raises(RuntimeError, match="would be lost"):
        command.downgrade(config, "0013")

    export = tmp / "audit.jsonl"
    config.cmd_opts = argparse.Namespace(x=[f"audit_export={export}"])
    command.downgrade(config, "0013")
    config.cmd_opts = None

    assert export.read_text(encoding="utf-8").count("user.created") == 1
    with engine.connect() as conn:
        assert dict(conn.execute(text("SELECT email, role FROM users")).all()) == {
            "u@x.com": "viewer", "a@x.com": "admin", "s@x.com": "admin",
        }
        assert conn.execute(text("SELECT to_regclass('audit_logs')")).scalar() is None
        assert conn.execute(text("SELECT COUNT(*) FROM pg_proc WHERE proname = 'audit_logs_immutable'")).scalar() == 0
    assert "audit_logs" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")  # and forward again
