"""sandbox previews + sandbox-preview system identity

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-26 00:00:00.000000

"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None

PREVIEW_USER_ID = "00000000-0000-0000-0000-000000000011"
PREVIEW_USER_EMAIL = "sandbox-preview@parcel.local"
PREVIEW_ROLE_NAME = "sandbox-preview"

# Argon2 hash of a random 32-byte secret never persisted anywhere. Login is
# impossible because no human knows the input. The shape passes the existing
# Argon2 verifier without needing a live verify.
_RANDOM_ARGON2 = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "ZmFrZXNhbHRmYWtlc2FsdA$"
    "QzCNk0r/m9YDXAm8e+EDOmJG44vF98Mwgg5SmygS3wA"
)


def upgrade() -> None:
    op.add_column(
        "sandbox_installs",
        sa.Column(
            "preview_status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        schema="shell",
    )
    op.add_column(
        "sandbox_installs",
        sa.Column("preview_error", sa.Text(), nullable=True),
        schema="shell",
    )
    op.add_column(
        "sandbox_installs",
        sa.Column(
            "previews",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="shell",
    )
    op.add_column(
        "sandbox_installs",
        sa.Column(
            "preview_started_at",
            sa.dialects.postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        schema="shell",
    )
    op.add_column(
        "sandbox_installs",
        sa.Column(
            "preview_finished_at",
            sa.dialects.postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        schema="shell",
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO shell.users (id, email, password_hash, is_active) "
            "VALUES (:id, :email, :hash, true) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": PREVIEW_USER_ID, "email": PREVIEW_USER_EMAIL, "hash": _RANDOM_ARGON2},
    )

    role_id = str(uuid.uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO shell.roles (id, name, description, is_builtin) "
            "VALUES (:id, :name, :desc, true) "
            "ON CONFLICT (name) DO NOTHING "
            "RETURNING id"
        ),
        {
            "id": role_id,
            "name": PREVIEW_ROLE_NAME,
            "desc": "Used by the sandbox preview renderer to drive headless Chromium",
        },
    )

    actual_role_id = bind.execute(
        sa.text("SELECT id FROM shell.roles WHERE name = :name"),
        {"name": PREVIEW_ROLE_NAME},
    ).scalar_one()

    bind.execute(
        sa.text(
            "INSERT INTO shell.user_roles (user_id, role_id) "
            "VALUES (:uid, :rid) "
            "ON CONFLICT DO NOTHING"
        ),
        {"uid": PREVIEW_USER_ID, "rid": actual_role_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    # user_roles rows for this user are removed implicitly by the FK's
    # ON DELETE CASCADE — that's why the role DELETE that follows is safe.
    bind.execute(
        sa.text("DELETE FROM shell.users WHERE id = :id"),
        {"id": PREVIEW_USER_ID},
    )
    bind.execute(
        sa.text("DELETE FROM shell.roles WHERE name = :name"),
        {"name": PREVIEW_ROLE_NAME},
    )
    op.drop_column("sandbox_installs", "preview_finished_at", schema="shell")
    op.drop_column("sandbox_installs", "preview_started_at", schema="shell")
    op.drop_column("sandbox_installs", "previews", schema="shell")
    op.drop_column("sandbox_installs", "preview_error", schema="shell")
    op.drop_column("sandbox_installs", "preview_status", schema="shell")
