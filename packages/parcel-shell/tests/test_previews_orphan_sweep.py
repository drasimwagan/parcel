from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.app import create_app
from parcel_shell.sandbox.models import SandboxInstall


@pytest.mark.asyncio
async def test_lifespan_sweeps_orphan_rendering(settings) -> None:
    """Shell lifespan flips stuck 'rendering' preview rows to 'failed' on boot."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    sandbox_id = uuid.uuid4()
    schema_name = f"mod_sandbox_{sandbox_id.hex[:8]}"
    async with factory() as s:
        s.add(
            SandboxInstall(
                id=sandbox_id,
                name="orphan",
                version="0.1.0",
                declared_capabilities=[],
                schema_name=schema_name,
                module_root="/tmp",
                url_prefix="/mod-sandbox/abc",
                gate_report={"passed": True, "findings": []},
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status="active",
                preview_status="rendering",
            )
        )
        await s.commit()

    app = create_app(settings=settings)
    async with LifespanManager(app):
        pass  # boot + shutdown; orphan sweep fires during startup

    async with factory() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        assert row is not None, "row must still exist after lifespan"
        assert row.preview_status == "failed"
        assert row.preview_error == "process_restart"
        await s.delete(row)
        await s.commit()
    await engine.dispose()
