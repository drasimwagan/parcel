"""create contact and company tables

Revision ID: 0001
Revises:
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("website", sa.Text()),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="mod_contacts",
    )

    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("first_name", sa.Text()),
        sa.Column("last_name", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mod_contacts.companies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="mod_contacts",
    )
    op.create_index("ix_contacts_email", "contacts", ["email"], schema="mod_contacts")
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"], schema="mod_contacts")


def downgrade() -> None:
    op.drop_index("ix_contacts_company_id", table_name="contacts", schema="mod_contacts")
    op.drop_index("ix_contacts_email", table_name="contacts", schema="mod_contacts")
    op.drop_table("contacts", schema="mod_contacts")
    op.drop_table("companies", schema="mod_contacts")
