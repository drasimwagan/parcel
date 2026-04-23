"""install_modules + modules.* permissions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


MODULE_PERMISSIONS = (
    ("modules.read", "View registered and discovered modules"),
    ("modules.install", "Install a discovered module"),
    ("modules.upgrade", "Run migrations for an already-installed module"),
    ("modules.uninstall", "Deactivate or remove a module"),
)


def upgrade() -> None:
    op.create_table(
        "installed_modules",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "capabilities",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("schema_name", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "installed_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_migrated_at", TIMESTAMP(timezone=True)),
        sa.Column("last_migrated_rev", sa.Text()),
        schema="shell",
    )

    # Idempotent inserts: an earlier shell boot (after the registry was extended
    # to include `modules.*` but before this migration ran) may have already
    # upserted these permissions via lifespan.sync_to_db.
    conn = op.get_bind()
    for name, description in MODULE_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO shell.permissions (name, description, module) "
                "VALUES (:name, :description, 'shell') "
                "ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"
            ),
            {"name": name, "description": description},
        )

    admin_id = conn.execute(sa.text("SELECT id FROM shell.roles WHERE name = 'admin'")).scalar_one()
    for name, _ in MODULE_PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO shell.role_permissions (role_id, permission_name) "
                "VALUES (:rid, :name) ON CONFLICT DO NOTHING"
            ),
            {"rid": admin_id, "name": name},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM shell.permissions WHERE name LIKE 'modules.%'"))
    op.drop_table("installed_modules", schema="shell")
