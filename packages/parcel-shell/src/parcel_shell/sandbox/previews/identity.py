"""Identity for the sandbox preview renderer.

Provides:
- `sync_preview_role`: idempotently assigns every Permission to the
  `sandbox-preview` builtin role (synced at render-time, not at migration
  time, so newly-installed modules' permissions get picked up).
- `mint_session_cookie`: creates a real `shell.sessions` row for the
  sandbox-preview user and returns `(session_id, signed cookie value)`.
- `revoke_session`: best-effort cleanup so `shell.sessions` doesn't grow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from parcel_shell.auth import sessions as sessions_service
from parcel_shell.auth.cookies import sign_session_id
from parcel_shell.config import Settings
from parcel_shell.rbac.models import (
    Permission,
    Role,
    role_permissions,
)
from parcel_shell.rbac.models import (
    Session as DbSession,
)

PREVIEW_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
PREVIEW_ROLE_NAME = "sandbox-preview"


async def sync_preview_role(sessionmaker: async_sessionmaker) -> None:
    """Assign every Permission name to the sandbox-preview role."""
    async with sessionmaker() as session, session.begin():
        role = (
            await session.execute(select(Role).where(Role.name == PREVIEW_ROLE_NAME))
        ).scalar_one()
        existing = set(
            (
                await session.execute(
                    select(role_permissions.c.permission_name).where(
                        role_permissions.c.role_id == role.id
                    )
                )
            )
            .scalars()
            .all()
        )
        all_names = set((await session.execute(select(Permission.name))).scalars().all())
        for name in all_names - existing:
            await session.execute(
                role_permissions.insert().values(role_id=role.id, permission_name=name)
            )


async def mint_session_cookie(
    sessionmaker: async_sessionmaker, settings: Settings
) -> tuple[uuid.UUID, str]:
    """Create a Session row for the preview user and sign its UUID for the cookie."""
    async with sessionmaker() as session, session.begin():
        db_session = await sessions_service.create_session(session, user_id=PREVIEW_USER_ID)
        session_id = db_session.id
    cookie_value = sign_session_id(session_id, secret=settings.session_secret)
    return session_id, cookie_value


async def revoke_session(sessionmaker: async_sessionmaker, session_id: uuid.UUID) -> None:
    """Mark the preview-renderer session revoked. No-op if missing."""
    async with sessionmaker() as session, session.begin():
        row = await session.get(DbSession, session_id)
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
