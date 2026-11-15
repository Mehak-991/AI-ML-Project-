"""three-role RBAC: user / admin / super_admin, plus access-token versioning

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-15

Data migration (capability-preserving, reversible):
    admin       -> super_admin   (full control, unchanged)
    ml_engineer -> admin         (keeps write access to ML resources)
    viewer      -> user          (read-only, unchanged)
    anything else -> user        (fail closed: unknown roles get the least privilege)

Schema:
- users.role server default 'viewer' -> 'user'
- CHECK constraint ck_users_role_valid so the database rejects unknown roles
- users.token_version (int, default 0): embedded in access tokens; bumping it revokes them

Downgrade reverses the mapping exactly (user -> viewer, admin -> ml_engineer,
super_admin -> admin).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_CHECK = "role IN ('user', 'admin', 'super_admin')"


def upgrade() -> None:
    # A single UPDATE with CASE evaluates every row against its *original* role, so the
    # admin -> super_admin and ml_engineer -> admin steps cannot cascade into each other.
    op.execute(
        sa.text(
            "UPDATE users SET role = CASE role "
            "WHEN 'admin' THEN 'super_admin' "
            "WHEN 'ml_engineer' THEN 'admin' "
            "WHEN 'viewer' THEN 'user' "
            "WHEN 'super_admin' THEN 'super_admin' "
            "WHEN 'user' THEN 'user' "
            "ELSE 'user' END"
        )
    )
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch.alter_column(
            "role",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default="user",
        )
        batch.create_check_constraint(op.f("ck_users_role_valid"), ROLE_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("ck_users_role_valid"), type_="check")
        batch.alter_column(
            "role",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            server_default="viewer",
        )
        batch.drop_column("token_version")
    op.execute(
        sa.text(
            "UPDATE users SET role = CASE role "
            "WHEN 'super_admin' THEN 'admin' "
            "WHEN 'admin' THEN 'ml_engineer' "
            "ELSE 'viewer' END"
        )
    )
