"""Sandbox preview render orchestration.

The `_render` coroutine is shared between the inline path
(`previews.queue.enqueue` → `asyncio.create_task`) and the worker path
(`previews.worker.render_sandbox_previews(ctx, sandbox_id)`). It opens its
own DB sessions through the supplied sessionmaker — never reuses a
request session.

`sweep_orphans` runs once at shell boot to flip stuck `'rendering'` rows
to `'failed'` after a process restart.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import async_playwright
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from parcel_shell.config import Settings
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall
from parcel_shell.sandbox.previews import identity, routes, seed_runner, storage

_log = structlog.get_logger("parcel_shell.sandbox.previews.runner")

VIEWPORTS = (375, 768, 1280)
MAX_SCREENSHOTS = 30
GOTO_TIMEOUT_MS = 10_000


async def _render(
    sandbox_id: uuid.UUID,
    sessionmaker: async_sessionmaker,
    app: Any,
    settings: Settings,
) -> None:
    """Render the previews for one sandbox. Catches all exceptions so the
    DB row always reaches a terminal status. Re-raises CancelledError so
    asyncio shutdown propagates."""
    async with sessionmaker() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        if row is None or row.status != "active":
            return
        row.preview_status = "rendering"
        row.preview_started_at = datetime.now(UTC)
        row.previews = []
        row.preview_error = None
        await s.commit()

    # Cache row.name and row fields before we lose the ORM object across sessions.
    module_name = row.name
    schema_name = row.schema_name
    module_root = row.module_root
    url_prefix = row.url_prefix

    session_id: uuid.UUID | None = None
    try:
        await identity.sync_preview_role(sessionmaker)
        session_id, cookie_value = await identity.mint_session_cookie(sessionmaker, settings)

        package_name = f"parcel_mod_{module_name}"
        short = sandbox_id.hex[:8]
        loaded = sandbox_service.load_sandbox_module(
            Path(module_root), package_name, sandbox_id=short
        )
        if hasattr(loaded, "module") and loaded.module.metadata is not None:
            loaded.module.metadata.schema = schema_name

        if seed_runner.has_seed(loaded):
            await seed_runner.run(loaded, sessionmaker)

        async with sessionmaker() as s:
            paths = await routes.resolve(loaded.module, s, schema_name)
        max_routes = MAX_SCREENSHOTS // len(VIEWPORTS)
        paths = paths[:max_routes]

        entries = await _drive_chromium(
            paths=paths,
            url_prefix=url_prefix,
            module_root=module_root,
            cookie_value=cookie_value,
            settings=settings,
        )

        async with sessionmaker() as s:
            row = await s.get(SandboxInstall, sandbox_id)
            if row is None:
                return
            row.previews = entries
            any_ok = any(e["status"] == "ok" for e in entries)
            row.preview_status = "ready" if any_ok else "failed"
            if not any_ok and entries:
                row.preview_error = "all routes errored"
            row.preview_finished_at = datetime.now(UTC)
            await s.commit()
    except asyncio.CancelledError:
        async with sessionmaker() as s:
            row = await s.get(SandboxInstall, sandbox_id)
            if row is not None:
                row.preview_status = "failed"
                row.preview_error = "cancelled"
                row.preview_finished_at = datetime.now(UTC)
                await s.commit()
        raise
    except BaseException as exc:  # noqa: BLE001
        _log.exception("sandbox.preview.render_failed", sandbox_id=str(sandbox_id))
        async with sessionmaker() as s:
            row = await s.get(SandboxInstall, sandbox_id)
            if row is not None:
                row.preview_status = "failed"
                row.preview_error = str(exc)[:500]
                row.preview_finished_at = datetime.now(UTC)
                await s.commit()
    finally:
        if session_id is not None:
            with contextlib.suppress(Exception):
                await identity.revoke_session(sessionmaker, session_id)


async def _drive_chromium(
    *,
    paths: list[str],
    url_prefix: str,
    module_root: str,
    cookie_value: str,
    settings: Settings,
) -> list[dict]:
    base_url = settings.public_base_url
    storage_dir = storage.previews_dir(module_root)
    storage_dir.mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for viewport in VIEWPORTS:
                context = await browser.new_context(
                    viewport={"width": viewport, "height": viewport * 2},
                    base_url=base_url,
                )
                try:
                    await context.add_cookies(
                        [
                            {
                                "name": "parcel_session",
                                "value": cookie_value,
                                "url": base_url,
                                "httpOnly": True,
                                "sameSite": "Lax",
                            }
                        ]
                    )
                    page = await context.new_page()
                    for path in paths:
                        url = f"{url_prefix}{path}"
                        filename = storage.filename_for(path, viewport)
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
                            await page.screenshot(
                                path=str(storage_dir / filename),
                                full_page=True,
                                type="png",
                            )
                            entries.append(
                                {
                                    "route": path,
                                    "viewport": viewport,
                                    "filename": filename,
                                    "status": "ok",
                                }
                            )
                        except Exception as exc:  # noqa: BLE001
                            entries.append(
                                {
                                    "route": path,
                                    "viewport": viewport,
                                    "filename": None,
                                    "status": "error",
                                    "error": str(exc)[:200],
                                }
                            )
                finally:
                    await context.close()
        finally:
            await browser.close()
    return entries


async def sweep_orphans(sessionmaker: async_sessionmaker) -> int:
    """Boot-time recovery — flip stuck 'rendering' rows to 'failed'."""
    async with sessionmaker() as s:
        result = await s.execute(
            update(SandboxInstall)
            .where(SandboxInstall.preview_status == "rendering")
            .values(
                preview_status="failed",
                preview_error="process_restart",
                preview_finished_at=datetime.now(UTC),
            )
        )
        await s.commit()
        return result.rowcount or 0
