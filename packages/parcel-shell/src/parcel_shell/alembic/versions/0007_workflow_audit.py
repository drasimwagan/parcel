"""workflow_audit table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-25 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, TIMESTAMP, UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_audit",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("workflow_slug", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("failed_action_index", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        schema="shell",
    )
    op.create_index(
        "ix_workflow_audit_module_slug_created",
        "workflow_audit",
        ["module", "workflow_slug", sa.text("created_at DESC")],
        schema="shell",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_audit_module_slug_created",
        table_name="workflow_audit",
        schema="shell",
    )
    op.drop_table("workflow_audit", schema="shell")
