"""RBAC v2: roles user/admin/superadmin and the append-only audit log

Revision ID: 0014
Revises: 0013

Legacy role mapping (explicit; nobody is promoted):
  viewer       -> user
  admin        -> admin (unchanged; NOT promoted to superadmin)
  ml_engineer  -> NO default. The migration aborts while such accounts exist unless the operator
                  passes an explicit mapping:  alembic -x ml_engineer=user upgrade 0014
                  (or -x ml_engineer=admin). Each mapped account gets an audit entry.
  anything else -> abort

No superadmin is created here; the server-side bootstrap CLI does that, naming the account.

Also: audit_logs table (append-only; PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE),
users.role server default 'user', and CHECK (role IN ('user','admin','superadmin','viewer')).
'viewer' stays allowed until the contract release so code deployed in the expand phase can still
write it (RBAC_STORE_LEGACY_VIEWER).

Downgrade (prefer restoring the pre-migration backup into a NEW database instead):
  user -> viewer, superadmin -> admin (the distinction between them is lost). audit_logs is
  dropped, so the downgrade refuses to run while entries exist unless
  `-x audit_export=<new file path>` is given; the entries are written there first (JSON lines).
"""

import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWN_ROLES = {"viewer", "ml_engineer", "admin", "user", "superadmin"}
ROLE_CHECK = "role IN ('user', 'admin', 'superadmin', 'viewer')"
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _x_args() -> dict[str, str]:
    try:
        return context.get_x_argument(as_dictionary=True)
    except Exception:  # no command-line options (programmatic use)
        return {}


def upgrade() -> None:
    bind = op.get_bind()
    counts = {row[0]: row[1] for row in bind.execute(sa.text("SELECT role, COUNT(*) FROM users GROUP BY role"))}

    unknown = sorted(set(counts) - KNOWN_ROLES)
    if unknown:
        raise RuntimeError(
            f"Migration 0014 aborted: unknown role value(s) {unknown} in users.role. "
            "Nothing was changed. Review and correct these accounts first."
        )
    ml_engineers = counts.get("ml_engineer", 0)
    mapping = _x_args().get("ml_engineer")
    if ml_engineers and mapping not in {"user", "admin"}:
        raise RuntimeError(
            f"Migration 0014 aborted: {ml_engineers} account(s) have the legacy role 'ml_engineer' "
            "and no explicit mapping was given. Nothing was changed and nobody was promoted. "
            "Review those accounts, then re-run with  -x ml_engineer=user  (least privilege) "
            "or  -x ml_engineer=admin."
        )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("target_email", sa.String(255), nullable=True),
        sa.Column("before", JSON_TYPE, nullable=True),
        sa.Column("after", JSON_TYPE, nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("client_ip", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"])
    op.create_index(op.f("ix_audit_logs_target_id"), "audit_logs", ["target_id"])

    # viewer -> user. admin stays admin. Passwords, ownership and every other column are untouched.
    bind.execute(sa.text("UPDATE users SET role = 'user' WHERE role = 'viewer'"))

    if ml_engineers:
        mapped = bind.execute(sa.text("SELECT id, email FROM users WHERE role = 'ml_engineer'")).all()
        bind.execute(sa.text("UPDATE users SET role = :role WHERE role = 'ml_engineer'"), {"role": mapping})
        # Typed columns, so each database converts UUIDs and JSON correctly (raw text() would not).
        audit = sa.table(
            "audit_logs",
            sa.column("id", sa.Uuid()),
            sa.column("action", sa.String()),
            sa.column("target_id", sa.Uuid()),
            sa.column("target_email", sa.String()),
            sa.column("before", JSON_TYPE),
            sa.column("after", JSON_TYPE),
            sa.column("detail", sa.Text()),
        )
        bind.execute(
            audit.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "action": "migration.role_mapped",
                    "target_id": uuid.UUID(str(user_id)),
                    "target_email": email,
                    "before": {"role": "ml_engineer"},
                    "after": {"role": mapping},
                    "detail": "explicit operator mapping supplied to migration 0014 (-x ml_engineer)",
                }
                for user_id, email in mapped
            ],
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "role", existing_type=sa.String(32), existing_nullable=False, server_default="user"
        )
        batch.create_check_constraint(op.f("ck_users_role"), ROLE_CHECK)

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION audit_logs_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs is append-only (% rejected)', TG_OP;
            END;
            $$
            """
        )
        op.execute(
            "CREATE TRIGGER audit_logs_no_change BEFORE UPDATE OR DELETE ON audit_logs "
            "FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()"
        )
        op.execute(
            "CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    entries = bind.execute(sa.text("SELECT COUNT(*) FROM audit_logs")).scalar() or 0
    if entries:
        target = _x_args().get("audit_export")
        if not target:
            raise RuntimeError(
                f"Downgrade of 0014 aborted: audit_logs holds {entries} entries that would be lost. "
                "Re-run with  -x audit_export=<path of a NEW file>  to save them first "
                "(or restore the pre-migration backup into a new database instead)."
            )
        path = Path(target)
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite the existing file {path}.")
        rows = bind.execute(sa.text("SELECT * FROM audit_logs ORDER BY created_at, id")).mappings().all()
        with path.open("x", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps({k: (v if isinstance(v, (int, float, bool, dict, list, type(None))) else str(v)) for k, v in row.items()}) + "\n")

    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS audit_logs_no_change ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")
    op.drop_table("audit_logs")

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("ck_users_role"), type_="check")
        batch.alter_column(
            "role", existing_type=sa.String(32), existing_nullable=False, server_default="viewer"
        )
    bind.execute(sa.text("UPDATE users SET role = 'viewer' WHERE role = 'user'"))
    bind.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'superadmin'"))
