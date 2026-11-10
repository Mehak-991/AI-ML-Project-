"""Admin bootstrap on real PostgreSQL: the advisory lock must make bootstrap one-time under races.

REQUIRES a disposable database via TEST_DATABASE_URL (see test_database.py). Runs in a throwaway
schema that is dropped afterwards.
"""

import threading

import pytest
from passlib.hash import pbkdf2_sha256
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ConflictError
from app.database.models.user import User
from app.services import auth_service
from tests.integration.test_database import pg_isolated_engine, requires_db  # noqa: F401

pytestmark = pytest.mark.integration

PASSWORD = "Str0ngPassw0rd"


@requires_db
def test_concurrent_bootstrap_creates_exactly_one_admin(pg_isolated_engine) -> None:  # noqa: F811
    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)
    attempts = 8
    barrier = threading.Barrier(attempts)
    outcomes: list[str] = []
    lock = threading.Lock()

    def attempt(index: int) -> None:
        with factory() as session:
            barrier.wait()
            try:
                auth_service.create_bootstrap_admin(session, f"root{index}@x.com", PASSWORD)
                result = "created"
            except ConflictError:
                result = "refused"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sorted(outcomes) == ["created"] + ["refused"] * (attempts - 1)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User).where(User.role == "admin")) == 1
        assert session.scalar(select(func.count()).select_from(User)) == 1


@requires_db
def test_legacy_hash_is_upgraded_on_postgres_login(pg_isolated_engine) -> None:  # noqa: F811
    from app.core.config import Settings
    from app.schemas.auth import UserLoginRequest

    factory = sessionmaker(bind=pg_isolated_engine, expire_on_commit=False)
    settings = Settings(_env_file=None, APP_ENV="testing")
    with factory() as session:
        admin = auth_service.create_bootstrap_admin(session, "root@x.com", PASSWORD)
        admin.hashed_password = pbkdf2_sha256.using(rounds=29000).hash(PASSWORD)
        session.commit()

    with factory() as session:
        user, tokens = auth_service.authenticate_user(
            session, settings, UserLoginRequest(email="root@x.com", password=PASSWORD)
        )
        assert tokens.access_token and user.role == "admin"

    with factory() as session:
        stored = session.scalar(select(User.hashed_password).where(User.email == "root@x.com"))
        assert stored.startswith("$argon2id$")
