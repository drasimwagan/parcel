"""create items

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        schema="mod_test",
    )


def downgrade() -> None:
    op.drop_table("items", schema="mod_test")
