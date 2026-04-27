from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import Role, User, user_roles

PREVIEW_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
PREVIEW_ROLE_NAME = "sandbox-preview"
PREVIEW_USER_EMAIL = "sandbox-preview@parcel.local"


@pytest.mark.asyncio
async def test_migration_adds_preview_columns(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='shell' AND table_name='sandbox_installs'"
            )
        )
    ).all()
    names = {r[0] for r in rows}
    assert {
        "preview_status",
        "preview_error",
        "previews",
        "preview_started_at",
        "preview_finished_at",
    } <= names


@pytest.mark.asyncio
async def test_migration_seeds_preview_user(db_session: AsyncSession) -> None:
    user = await db_session.get(User, PREVIEW_USER_ID)
    assert user is not None
    assert user.email == PREVIEW_USER_EMAIL
    assert user.is_active is True


@pytest.mark.asyncio
async def test_migration_seeds_preview_role(db_session: AsyncSession) -> None:
    role = (
        await db_session.execute(select(Role).where(Role.name == PREVIEW_ROLE_NAME))
    ).scalar_one_or_none()
    assert role is not None
    assert role.is_builtin is True


@pytest.mark.asyncio
async def test_migration_binds_user_to_role(db_session: AsyncSession) -> None:
    role = (
        await db_session.execute(select(Role).where(Role.name == PREVIEW_ROLE_NAME))
    ).scalar_one()
    rows = (
        await db_session.execute(
            select(user_roles.c.user_id).where(
                user_roles.c.user_id == PREVIEW_USER_ID,
                user_roles.c.role_id == role.id,
            )
        )
    ).all()
    assert len(rows) == 1


def test_migration_does_not_seed_role_permissions() -> None:
    """Role-permission rows are synced at render time, not by migration.

    Verified by inspecting the migration source rather than the live DB,
    because other preview tests (test_previews_identity.py) commit role-
    permission rows via sync_preview_role() and may run before this test
    depending on the pytest invocation order.
    """
    from pathlib import Path

    versions_dir = Path(__file__).parent.parent / "src" / "parcel_shell" / "alembic" / "versions"
    migration_file = versions_dir / "0009_sandbox_previews.py"
    assert migration_file.exists(), f"Migration file not found: {migration_file}"
    source = migration_file.read_text()
    # The upgrade() function must not touch role_permissions at all.
    assert (
        "role_permissions" not in source
    ), "Migration 0009 must not seed role_permissions — sync happens at render time"
