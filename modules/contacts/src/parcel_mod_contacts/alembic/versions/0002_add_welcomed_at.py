"""add welcomed_at to contacts

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("welcomed_at", TIMESTAMP(timezone=True), nullable=True),
        schema="mod_contacts",
    )


def downgrade() -> None:
    op.drop_column("contacts", "welcomed_at", schema="mod_contacts")
