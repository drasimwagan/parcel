"""ai_sessions + ai_turns tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'(untitled)'"),
        ),
        sa.Column(
            "created_at",
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
        schema="shell",
    )
    op.create_index(
        "ix_ai_sessions_owner_updated",
        "ai_sessions",
        ["owner_id", sa.text("updated_at DESC")],
        schema="shell",
    )

    op.create_table(
        "ai_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.ai_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("sandbox_id", UUID(as_uuid=True)),
        sa.Column("failure_kind", sa.Text()),
        sa.Column("failure_message", sa.Text()),
        sa.Column("gate_report", JSONB()),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("session_id", "idx", name="uq_ai_turns_session_idx"),
        schema="shell",
    )
    op.create_index(
        "ix_ai_turns_session_idx",
        "ai_turns",
        ["session_id", "idx"],
        schema="shell",
    )
    op.create_index(
        "ix_ai_turns_status",
        "ai_turns",
        ["status"],
        schema="shell",
    )


def downgrade() -> None:
    op.drop_index("ix_ai_turns_status", "ai_turns", schema="shell")
    op.drop_index("ix_ai_turns_session_idx", "ai_turns", schema="shell")
    op.drop_table("ai_turns", schema="shell")
    op.drop_index("ix_ai_sessions_owner_updated", "ai_sessions", schema="shell")
    op.drop_table("ai_sessions", schema="shell")
