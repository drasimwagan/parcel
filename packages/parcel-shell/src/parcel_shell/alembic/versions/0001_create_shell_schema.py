"""create shell schema

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""

from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "shell"')


def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "shell" CASCADE')
