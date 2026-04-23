"""auth + RBAC

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


SHELL_PERMISSIONS = (
    ("users.read", "List and view user accounts"),
    ("users.write", "Create, update, and deactivate user accounts"),
    ("roles.read", "List and view roles"),
    ("roles.write", "Create, update, and delete roles; assign permissions to roles"),
    ("users.roles.assign", "Assign and unassign roles on users"),
    ("sessions.read", "List another user's sessions"),
    ("sessions.revoke", "Revoke another user's sessions"),
    ("permissions.read", "List registered permissions"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="shell",
    )

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", TIMESTAMP(timezone=True)),
        sa.Column("ip_address", INET()),
        sa.Column("user_agent", sa.Text()),
        schema="shell",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema="shell")
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], schema="shell")

    op.create_table(
        "permissions",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("module", sa.Text(), nullable=False, server_default="shell"),
        schema="shell",
    )

    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        schema="shell",
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="shell",
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            UUID(as_uuid=True),
            sa.ForeignKey("shell.roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_name",
            sa.Text(),
            sa.ForeignKey("shell.permissions.name", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="shell",
    )

    # Seed shell permissions.
    op.bulk_insert(
        sa.table(
            "permissions",
            sa.column("name", sa.Text()),
            sa.column("description", sa.Text()),
            sa.column("module", sa.Text()),
            schema="shell",
        ),
        [
            {"name": name, "description": description, "module": "shell"}
            for name, description in SHELL_PERMISSIONS
        ],
    )

    # Seed the built-in admin role and attach every shell permission.
    conn = op.get_bind()
    admin_id = conn.execute(
        sa.text(
            "INSERT INTO shell.roles (id, name, description, is_builtin) "
            "VALUES (gen_random_uuid(), 'admin', 'Built-in administrator role', true) "
            "RETURNING id"
        )
    ).scalar_one()

    conn.execute(
        sa.text(
            "INSERT INTO shell.role_permissions (role_id, permission_name) "
            "SELECT :rid, name FROM shell.permissions"
        ),
        {"rid": admin_id},
    )


def downgrade() -> None:
    op.drop_table("role_permissions", schema="shell")
    op.drop_table("user_roles", schema="shell")
    op.drop_table("roles", schema="shell")
    op.drop_table("permissions", schema="shell")
    op.drop_index("ix_sessions_expires_at", table_name="sessions", schema="shell")
    op.drop_index("ix_sessions_user_id", table_name="sessions", schema="shell")
    op.drop_table("sessions", schema="shell")
    op.drop_table("users", schema="shell")
