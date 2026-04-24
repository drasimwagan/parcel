"""sandbox_installs + sandbox.* permissions

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


SANDBOX_PERMISSIONS = (
    ("sandbox.read", "View sandbox installs and gate reports"),
    ("sandbox.install", "Upload and install candidates into the sandbox"),
    ("sandbox.promote", "Promote a sandbox install to a real module install"),
)


def upgrade() -> None:
    op.create_table(
        "sandbox_installs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "declared_capabilities",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("schema_name", sa.Text(), nullable=False, unique=True),
        sa.Column("module_root", sa.Text(), nullable=False),
        sa.Column("url_prefix", sa.Text(), nullable=False),
        sa.Column("gate_report", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("promoted_at", TIMESTAMP(timezone=True)),
        sa.Column("promoted_to_name", sa.Text()),
        schema="shell",
    )
    op.create_index(
        "ix_sandbox_installs_status",
        "sandbox_installs",
        ["status"],
        schema="shell",
    )
    op.create_index(
        "ix_sandbox_installs_expires_at",
        "sandbox_installs",
        ["expires_at"],
        schema="shell",
    )

    conn = op.get_bind()
    for name, description in SANDBOX_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO shell.permissions (name, description, module) "
                "VALUES (:name, :description, 'shell') "
                "ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"
            ),
            {"name": name, "description": description},
        )

    admin_id = conn.execute(
        sa.text("SELECT id FROM shell.roles WHERE name = 'admin'")
    ).scalar_one()
    for name, _ in SANDBOX_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO shell.role_permissions (role_id, permission_name) "
                "VALUES (:rid, :name) ON CONFLICT DO NOTHING"
            ),
            {"rid": admin_id, "name": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM shell.permissions WHERE name LIKE 'sandbox.%'"))
    op.drop_index("ix_sandbox_installs_expires_at", "sandbox_installs", schema="shell")
    op.drop_index("ix_sandbox_installs_status", "sandbox_installs", schema="shell")
    op.drop_table("sandbox_installs", schema="shell")
