"""ai.generate permission

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO shell.permissions (name, description, module) "
            "VALUES ('ai.generate', "
            "'Generate a module draft via the Claude generator', 'shell') "
            "ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"
        )
    )
    admin_id = conn.execute(
        sa.text("SELECT id FROM shell.roles WHERE name = 'admin'")
    ).scalar_one()
    conn.execute(
        sa.text(
            "INSERT INTO shell.role_permissions (role_id, permission_name) "
            "VALUES (:rid, 'ai.generate') ON CONFLICT DO NOTHING"
        ),
        {"rid": admin_id},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM shell.permissions WHERE name = 'ai.generate'"))
