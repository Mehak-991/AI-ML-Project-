"""Argon2id hashing, verification of legacy hashes, and rehash-on-login."""

import pytest
from fastapi.testclient import TestClient
from passlib.hash import bcrypt, pbkdf2_sha256
from sqlalchemy import select

from app.core import security
from app.database.models.user import User
from app.database.session import get_db
from app.main import create_app

API = "/api/v1"
PASSWORD = "Str0ngPassw0rd"


def test_new_hashes_are_argon2id_with_documented_parameters() -> None:
    hashed = security.hash_password(PASSWORD)
    assert hashed.startswith("$argon2id$")
    assert f"m={security.ARGON2_MEMORY_COST_KIB},t={security.ARGON2_TIME_COST},p=1" in hashed
    assert security.verify_password(PASSWORD, hashed)
    assert not security.verify_password(PASSWORD + "x", hashed)
    assert hashed != security.hash_password(PASSWORD), "each hash must use a fresh salt"


def test_legacy_pbkdf2_hash_still_verifies_and_is_marked_for_upgrade() -> None:
    # The format used by every account created before Argon2id (passlib's 29,000-round default).
    legacy = pbkdf2_sha256.using(rounds=29000).hash(PASSWORD)
    assert security.verify_password(PASSWORD, legacy)
    ok, upgraded = security.verify_and_rehash(PASSWORD, legacy)
    assert ok
    assert upgraded is not None and upgraded.startswith("$argon2id$")
    assert security.verify_password(PASSWORD, upgraded)


def test_legacy_bcrypt_hash_is_upgraded_too() -> None:
    legacy = bcrypt.using(rounds=4).hash(PASSWORD)
    ok, upgraded = security.verify_and_rehash(PASSWORD, legacy)
    assert ok and upgraded is not None and upgraded.startswith("$argon2id$")


def test_current_hash_is_not_rewritten_on_every_login() -> None:
    current = security.hash_password(PASSWORD)
    assert security.verify_and_rehash(PASSWORD, current) == (True, None)


def test_wrong_password_never_produces_a_replacement_hash() -> None:
    legacy = pbkdf2_sha256.using(rounds=29000).hash(PASSWORD)
    assert security.verify_and_rehash("not-the-password", legacy) == (False, None)


def test_unknown_account_fails_without_a_hash() -> None:
    assert security.verify_and_rehash(PASSWORD, None) == (False, None)


@pytest.fixture
def client(make_settings, session_factory):
    app = create_app(make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False))

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _stored_hash(session_factory, email: str) -> str:
    with session_factory() as session:
        return session.scalar(select(User.hashed_password).where(User.email == email))


def _force_legacy_hash(session_factory, email: str) -> str:
    legacy = pbkdf2_sha256.using(rounds=29000).hash(PASSWORD)
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        user.hashed_password = legacy
        session.commit()
    return legacy


def test_login_upgrades_a_legacy_hash_and_the_account_keeps_working(client, session_factory) -> None:
    client.post(f"{API}/auth/register", json={"email": "old@x.com", "password": PASSWORD})
    legacy = _force_legacy_hash(session_factory, "old@x.com")

    first = client.post(f"{API}/auth/login", json={"email": "old@x.com", "password": PASSWORD})
    assert first.status_code == 200
    upgraded = _stored_hash(session_factory, "old@x.com")
    assert upgraded != legacy and upgraded.startswith("$argon2id$")

    second = client.post(f"{API}/auth/login", json={"email": "old@x.com", "password": PASSWORD})
    assert second.status_code == 200
    assert _stored_hash(session_factory, "old@x.com") == upgraded, "no rewrite once upgraded"


def test_rehash_switch_keeps_legacy_hashes_readable_by_older_releases(make_settings, session_factory) -> None:
    """Staged rollout: with PASSWORD_REHASH_ON_LOGIN=false the login works but nothing is rewritten."""
    app = create_app(
        make_settings(APP_ENV="testing", RATE_LIMIT_ENABLED=False, PASSWORD_REHASH_ON_LOGIN=False)
    )

    def _get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app, raise_server_exceptions=False) as switched_off:
        switched_off.post(f"{API}/auth/register", json={"email": "old@x.com", "password": PASSWORD})
        legacy = _force_legacy_hash(session_factory, "old@x.com")
        response = switched_off.post(f"{API}/auth/login", json={"email": "old@x.com", "password": PASSWORD})
        assert response.status_code == 200
        assert _stored_hash(session_factory, "old@x.com") == legacy
        # New registrations are still Argon2id regardless of the switch.
        switched_off.post(f"{API}/auth/register", json={"email": "new@x.com", "password": PASSWORD})
        assert _stored_hash(session_factory, "new@x.com").startswith("$argon2id$")


def test_rehash_is_on_by_default() -> None:
    from app.core.config import Settings

    assert Settings(_env_file=None).PASSWORD_REHASH_ON_LOGIN is True


def test_failed_login_leaves_a_legacy_hash_untouched(client, session_factory) -> None:
    client.post(f"{API}/auth/register", json={"email": "old@x.com", "password": PASSWORD})
    legacy = _force_legacy_hash(session_factory, "old@x.com")
    response = client.post(f"{API}/auth/login", json={"email": "old@x.com", "password": "Wr0ngPassword"})
    assert response.status_code == 401
    assert _stored_hash(session_factory, "old@x.com") == legacy


def test_deactivated_account_hash_is_not_rewritten(client, session_factory) -> None:
    client.post(f"{API}/auth/register", json={"email": "off@x.com", "password": PASSWORD})
    legacy = _force_legacy_hash(session_factory, "off@x.com")
    with session_factory() as session:
        session.scalar(select(User).where(User.email == "off@x.com")).is_active = False
        session.commit()
    response = client.post(f"{API}/auth/login", json={"email": "off@x.com", "password": PASSWORD})
    assert response.status_code == 401
    assert _stored_hash(session_factory, "off@x.com") == legacy


def test_changed_password_is_stored_as_argon2id(client, session_factory) -> None:
    client.post(f"{API}/auth/register", json={"email": "chg@x.com", "password": PASSWORD})
    token = client.post(f"{API}/auth/login", json={"email": "chg@x.com", "password": PASSWORD}).json()[
        "access_token"
    ]
    response = client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "An0therStr0ngOne"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert _stored_hash(session_factory, "chg@x.com").startswith("$argon2id$")
