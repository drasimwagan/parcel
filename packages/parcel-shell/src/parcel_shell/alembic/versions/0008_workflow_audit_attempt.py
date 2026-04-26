"""workflow_audit.attempt

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_audit",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        schema="shell",
    )


def downgrade() -> None:
    op.drop_column("workflow_audit", "attempt", schema="shell")
