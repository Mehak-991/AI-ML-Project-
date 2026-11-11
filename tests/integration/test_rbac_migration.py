"""Migration 0014 (RBAC v2) through real Alembic on a throwaway SQLite file.

It starts from a database at revision 0013 holding legacy roles, then checks the mapping, the
abort conditions, that nothing is promoted, that passwords and ownership survive untouched, and
that the downgrade is guarded and reversible. PostgreSQL-specific behaviour (triggers, locks) is
in test_rbac_pg.py.
"""

import argparse
import json
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import get_settings

ROOT = Path(__file__).resolve().parents[2]

# Distinct hashes so "unchanged" is checkable per account.
HASHES = {
    "viewer": "$pbkdf2-sha256$29000$viewerhash",
    "admin": "$pbkdf2-sha256$29000$adminhash",
    "ml": "$pbkdf2-sha256$29000$mlhash",
    "ml2": "$pbkdf2-sha256$29000$mlhash2",
}


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'rbac.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    engine = create_engine(url)
    yield config, engine, tmp_path
    engine.dispose()
    get_settings.cache_clear()


def _x(config: Config, *pairs: str) -> None:
    """The programmatic equivalent of `alembic -x key=value ...`."""
    config.cmd_opts = argparse.Namespace(x=list(pairs))


def _seed_legacy(engine, *, ml_engineers: int = 0, extra_role: str | None = None) -> dict[str, str]:
    """Insert legacy accounts and one dataset owned by the admin. Returns email -> id."""
    ids: dict[str, str] = {}
    rows = [("viewer@x.com", "viewer", HASHES["viewer"]), ("admin@x.com", "admin", HASHES["admin"])]
    for index in range(ml_engineers):
        rows.append((f"ml{index}@x.com", "ml_engineer", HASHES["ml"] if index == 0 else HASHES["ml2"]))
    if extra_role:
        rows.append(("odd@x.com", extra_role, "$pbkdf2-sha256$29000$odd"))
    with engine.begin() as conn:
        for email, role, hashed in rows:
            user_id = uuid.uuid4().hex
            ids[email] = user_id
            conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) "
                    "VALUES (:id, :email, :h, '', :role, 1)"
                ),
                {"id": user_id, "email": email, "h": hashed, "role": role},
            )
        conn.execute(
            text(
                "INSERT INTO datasets (id, name, original_filename, stored_filename, file_format, size_bytes, "
                "sha256, n_rows, n_columns, columns, owner_id) VALUES (:id, 'd', 'd.csv', 'd-stored.csv', 'csv', "
                "1, :sha, 1, 1, '[]', :owner)"
            ),
            {"id": uuid.uuid4().hex, "sha": "0" * 64, "owner": ids["admin@x.com"]},
        )
    return ids


def _snapshot(engine) -> dict:
    with engine.connect() as conn:
        users = conn.execute(text("SELECT id, email, hashed_password, role, is_active FROM users ORDER BY email")).all()
        owner = conn.execute(text("SELECT owner_id FROM datasets")).scalar()
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {"users": [tuple(u) for u in users], "dataset_owner": owner, "revision": revision}


def _roles(engine) -> dict[str, str]:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT email, role FROM users")).all())


# --- the mapping --------------------------------------------------------------------------------


def test_viewer_becomes_user_admin_stays_admin_and_nobody_is_promoted(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    ids = _seed_legacy(engine)
    before = _snapshot(engine)

    command.upgrade(config, "0014")

    assert _roles(engine) == {"viewer@x.com": "user", "admin@x.com": "admin"}
    assert "superadmin" not in _roles(engine).values(), "the migration never creates or promotes a superadmin"
    after = _snapshot(engine)
    assert after["revision"] == "0014"
    # passwords, ids, status and resource ownership are untouched
    assert [(i, e, h, a) for i, e, h, _, a in after["users"]] == [(i, e, h, a) for i, e, h, _, a in before["users"]]
    assert after["dataset_owner"] == before["dataset_owner"] == ids["admin@x.com"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar() == 0


def test_server_default_and_constraint_after_upgrade(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0014")
    columns = {c["name"]: c for c in inspect(engine).get_columns("users")}
    assert "user" in str(columns["role"]["default"])
    insert = "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) VALUES (:i, :e, 'h', '', :r, 1)"
    for role in ("user", "admin", "superadmin", "viewer"):
        with engine.begin() as conn:
            conn.execute(text(insert), {"i": uuid.uuid4().hex, "e": f"{role}@x.com", "r": role})
    for bad in ("ml_engineer", "root", "ADMIN", ""):
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(insert), {"i": uuid.uuid4().hex, "e": f"{bad or 'empty'}@x.com", "r": bad})
    with engine.begin() as conn:  # an account created without a role is a read-only user
        conn.execute(
            text("INSERT INTO users (id, email, hashed_password, full_name, is_active) VALUES (:i, 'norole@x.com', 'h', '', 1)"),
            {"i": uuid.uuid4().hex},
        )
        assert conn.execute(text("SELECT role FROM users WHERE email='norole@x.com'")).scalar() == "user"


# --- aborts --------------------------------------------------------------------------------------


def test_an_unmapped_ml_engineer_aborts_and_changes_nothing(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    _seed_legacy(engine, ml_engineers=2)
    before = _snapshot(engine)

    with pytest.raises(RuntimeError, match=r"2 account\(s\).*'ml_engineer'.*-x ml_engineer"):
        command.upgrade(config, "0014")

    assert _snapshot(engine) == before, "an aborted migration leaves the database exactly as it was"
    assert "audit_logs" not in inspect(engine).get_table_names()
    assert set(_roles(engine).values()) == {"viewer", "admin", "ml_engineer"}


@pytest.mark.parametrize("mapping", ["superadmin", "viewer", "ml_engineer", "", "root"])
def test_only_user_or_admin_are_accepted_as_an_ml_engineer_mapping(db, mapping) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    _seed_legacy(engine, ml_engineers=1)
    before = _snapshot(engine)
    _x(config, f"ml_engineer={mapping}")
    with pytest.raises(RuntimeError, match="aborted"):
        command.upgrade(config, "0014")
    assert _snapshot(engine) == before


def test_an_unknown_role_value_aborts(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    _seed_legacy(engine, extra_role="overlord")
    before = _snapshot(engine)
    with pytest.raises(RuntimeError, match=r"unknown role value\(s\) \['overlord'\]"):
        command.upgrade(config, "0014")
    assert _snapshot(engine) == before


# --- explicit ml_engineer mapping -----------------------------------------------------------------


@pytest.mark.parametrize("mapping", ["user", "admin"])
def test_an_explicit_ml_engineer_mapping_is_applied_and_audited(db, mapping) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    ids = _seed_legacy(engine, ml_engineers=2)
    _x(config, f"ml_engineer={mapping}")

    command.upgrade(config, "0014")

    roles = _roles(engine)
    assert roles["ml0@x.com"] == roles["ml1@x.com"] == mapping
    assert roles["viewer@x.com"] == "user" and roles["admin@x.com"] == "admin"
    with engine.connect() as conn:
        entries = conn.execute(
            text("SELECT action, target_id, target_email, before, after, detail FROM audit_logs ORDER BY target_email")
        ).all()
        hashes = dict(conn.execute(text("SELECT email, hashed_password FROM users")).all())
    assert [e[0] for e in entries] == ["migration.role_mapped", "migration.role_mapped"]
    assert [e[2] for e in entries] == ["ml0@x.com", "ml1@x.com"]
    assert [e[1] for e in entries] == [ids["ml0@x.com"], ids["ml1@x.com"]]
    for entry in entries:
        assert json.loads(entry[3]) == {"role": "ml_engineer"} and json.loads(entry[4]) == {"role": mapping}
        assert "-x ml_engineer" in entry[5]
    assert hashes["ml0@x.com"] == HASHES["ml"] and hashes["ml1@x.com"] == HASHES["ml2"]
    assert "superadmin" not in roles.values()


# --- downgrade and re-upgrade ---------------------------------------------------------------------


def test_downgrade_refuses_to_discard_audit_entries_without_an_export(db) -> None:
    config, engine, tmp = db
    command.upgrade(config, "0013")
    _seed_legacy(engine, ml_engineers=1)
    _x(config, "ml_engineer=user")
    command.upgrade(config, "0014")
    config.cmd_opts = None
    with pytest.raises(RuntimeError, match="would be lost"):
        command.downgrade(config, "0013")
    assert _snapshot(engine)["revision"] == "0014" and "audit_logs" in inspect(engine).get_table_names()

    export = tmp / "audit-export.jsonl"
    _x(config, f"audit_export={export}")
    command.downgrade(config, "0013")
    lines = [json.loads(line) for line in export.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1 and lines[0]["action"] == "migration.role_mapped"

    # a second export to the same path is refused rather than overwritten
    command.upgrade(config, "0014")  # no ml_engineer left, so no mapping needed and no entries
    assert "audit_logs" in inspect(engine).get_table_names()


def test_downgrade_restores_the_legacy_vocabulary_and_drops_the_new_objects(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0014")
    insert = "INSERT INTO users (id, email, hashed_password, full_name, role, is_active) VALUES (:i, :e, 'h', '', :r, 1)"
    with engine.begin() as conn:
        for email, role in (("u@x.com", "user"), ("a@x.com", "admin"), ("s@x.com", "superadmin")):
            conn.execute(text(insert), {"i": uuid.uuid4().hex, "e": email, "r": role})

    command.downgrade(config, "0013")  # no audit entries, so no export is needed

    assert _roles(engine) == {"u@x.com": "viewer", "a@x.com": "admin", "s@x.com": "admin"}
    assert "audit_logs" not in inspect(engine).get_table_names()
    columns = {c["name"]: c for c in inspect(engine).get_columns("users")}
    assert "viewer" in str(columns["role"]["default"])
    with engine.begin() as conn:  # the CHECK is gone: legacy values are valid again
        conn.execute(text(insert), {"i": uuid.uuid4().hex, "e": "ml@x.com", "r": "ml_engineer"})


def test_export_never_overwrites_an_existing_file(db) -> None:
    config, engine, tmp = db
    command.upgrade(config, "0014")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_logs (id, action) VALUES (:i, 'user.created')"), {"i": uuid.uuid4().hex})
    existing = tmp / "keep.jsonl"
    existing.write_text("precious", encoding="utf-8")
    _x(config, f"audit_export={existing}")
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        command.downgrade(config, "0013")
    assert existing.read_text(encoding="utf-8") == "precious"
    assert "audit_logs" in inspect(engine).get_table_names()


def test_upgrade_after_downgrade_and_a_repeated_upgrade_are_clean(db) -> None:
    config, engine, _ = db
    command.upgrade(config, "0013")
    _seed_legacy(engine)
    command.upgrade(config, "0014")
    command.downgrade(config, "0013")
    assert set(_roles(engine).values()) == {"viewer", "admin"}
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # idempotent
    assert _roles(engine) == {"viewer@x.com": "user", "admin@x.com": "admin"}
    assert _snapshot(engine)["revision"] == "0014"
