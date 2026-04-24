from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.config import Settings
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _zip_of(src: Path, dst: Path) -> bytes:
    with zipfile.ZipFile(dst, "w") as zf:
        for p in src.rglob("*"):
            if "__pycache__" in p.parts or p.suffix in {".pyc"}:
                continue
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(src)))
    return dst.read_bytes()


async def _with_fresh_session(settings: Settings):
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


@pytest.mark.asyncio
async def test_create_sandbox_happy_path(
    committing_app: FastAPI, settings: Settings, tmp_path: Path
) -> None:
    blob = _zip_of(CONTACTS_SRC, tmp_path / "contacts.zip")
    engine, factory = await _with_fresh_session(settings)
    try:
        async with factory() as db:
            row = await sandbox_service.create_sandbox(
                db,
                source_zip_bytes=blob,
                app=committing_app,
                settings=settings,
            )
            await db.commit()
            assert isinstance(row.id, UUID)
            assert row.name == "contacts"
            assert row.gate_report["passed"] is True
            has = (
                await db.execute(
                    sa_text(
                        "SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :s"
                    ),
                    {"s": row.schema_name},
                )
            ).scalar()
            assert has == 1
            # Cleanup
            await sandbox_service.dismiss_sandbox(db, row.id, committing_app)
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_sandbox_gate_rejection_leaves_no_state(
    committing_app: FastAPI, settings: Settings, tmp_path: Path
) -> None:
    # Build a minimal bad module that imports os without declaring capability.
    mod = tmp_path / "bad_mod"
    pkg = mod / "src" / "parcel_mod_bad"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "import os\n"
        "from parcel_sdk import Module\n"
        "module = Module(name='bad', version='0.1.0')\n"
    )
    (mod / "pyproject.toml").write_text(
        '[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n'
    )
    blob = _zip_of(mod, tmp_path / "bad.zip")

    engine, factory = await _with_fresh_session(settings)
    try:
        async with factory() as db:
            with pytest.raises(sandbox_service.GateRejected) as ei:
                await sandbox_service.create_sandbox(
                    db,
                    source_zip_bytes=blob,
                    app=committing_app,
                    settings=settings,
                )
            report = ei.value.report
            assert report.passed is False
            assert any(f.rule == "ast.blocked_import.os" for f in report.errors)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dismiss_sandbox_drops_schema(
    committing_app: FastAPI, settings: Settings, tmp_path: Path
) -> None:
    blob = _zip_of(CONTACTS_SRC, tmp_path / "contacts.zip")
    engine, factory = await _with_fresh_session(settings)
    try:
        async with factory() as db:
            row = await sandbox_service.create_sandbox(
                db, source_zip_bytes=blob, app=committing_app, settings=settings
            )
            await db.commit()
            sb_id = row.id
            schema = row.schema_name
            root = row.module_root
        async with factory() as db:
            await sandbox_service.dismiss_sandbox(db, sb_id, committing_app)
            await db.commit()
            reloaded = await db.get(SandboxInstall, sb_id)
            assert reloaded is not None
            assert reloaded.status == "dismissed"
            has = (
                await db.execute(
                    sa_text(
                        "SELECT 1 FROM information_schema.schemata "
                        "WHERE schema_name = :s"
                    ),
                    {"s": schema},
                )
            ).scalar()
            assert has is None
            assert not Path(root).exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prune_expired_dismisses_old_active_rows(
    committing_app: FastAPI, settings: Settings, tmp_path: Path
) -> None:
    from datetime import UTC, datetime, timedelta

    blob = _zip_of(CONTACTS_SRC, tmp_path / "contacts.zip")
    engine, factory = await _with_fresh_session(settings)
    try:
        async with factory() as db:
            row = await sandbox_service.create_sandbox(
                db, source_zip_bytes=blob, app=committing_app, settings=settings
            )
            await db.commit()
            sb_id = row.id

        # Rewind expires_at to the past.
        async with factory() as db:
            await db.execute(
                sa_text(
                    "UPDATE shell.sandbox_installs "
                    "SET expires_at = :t WHERE id = :id"
                ),
                {"t": datetime.now(UTC) - timedelta(days=1), "id": sb_id},
            )
            await db.commit()

        async with factory() as db:
            count = await sandbox_service.prune_expired(
                db, committing_app, now=datetime.now(UTC)
            )
            await db.commit()
            assert count == 1
            row = await db.get(SandboxInstall, sb_id)
            assert row is not None
            assert row.status == "dismissed"
    finally:
        await engine.dispose()
