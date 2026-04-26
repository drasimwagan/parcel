from __future__ import annotations

import contextlib
import types
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_sdk import Module
from parcel_shell.sandbox.models import SandboxInstall
from parcel_shell.sandbox.previews import runner


def _make_loaded_module() -> types.ModuleType:
    """A bare loaded module — no seed, no router."""
    pkg = types.ModuleType("fake_pkg__sandbox_x")
    pkg.module = Module(name="t", version="0.1.0")
    return pkg


@contextlib.asynccontextmanager
async def _fake_playwright(captured: list[tuple[str, int, str]]):
    """Stand-in for `async_playwright()` — captures (url, viewport, filename)."""
    pw = MagicMock()
    browser = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)
    browser.close = AsyncMock()

    def _new_context(**kwargs):
        ctx = AsyncMock()
        viewport = kwargs.get("viewport", {}).get("width")

        async def _new_page():
            page = AsyncMock()

            async def _goto(url, **_):
                pass

            page.goto = _goto

            async def _screenshot(path: str = "", **_):
                captured.append(("ok", viewport, path))
                # Touch the file so storage validation finds it later.
                Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 100)

            page.screenshot = _screenshot
            return page

        ctx.new_page = _new_page
        ctx.add_cookies = AsyncMock()
        ctx.close = AsyncMock()
        return ctx

    browser.new_context = AsyncMock(side_effect=lambda **k: _new_context(**k))

    yield pw


@pytest.mark.asyncio
async def test_render_marks_ready_with_entries(
    migrations_applied: str, settings, tmp_path: Path
) -> None:
    """End-to-end with mocked Playwright, real DB, real storage. One route → 3 viewports."""
    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    sandbox_id = uuid.uuid4()
    module_root = tmp_path / "sandbox-x"
    module_root.mkdir()

    async with factory() as s:
        s.add(
            SandboxInstall(
                id=sandbox_id,
                name="x",
                version="0.1.0",
                declared_capabilities=[],
                schema_name=f"mod_sandbox_{sandbox_id.hex[:8]}",
                module_root=str(module_root),
                url_prefix="/mod-sandbox/abc",
                gate_report={"passed": True, "findings": []},
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status="active",
                preview_status="pending",
            )
        )
        await s.commit()

    captured: list[tuple[str, int, str]] = []

    async def _fake_resolve(module, session, schema_name):
        return ["/page"]

    fake_loaded = _make_loaded_module()

    with (
        patch(
            "parcel_shell.sandbox.previews.runner.async_playwright",
            lambda: _fake_playwright(captured),
        ),
        patch(
            "parcel_shell.sandbox.previews.runner.routes.resolve",
            _fake_resolve,
        ),
        patch(
            "parcel_shell.sandbox.previews.runner.sandbox_service.load_sandbox_module",
            lambda *a, **kw: fake_loaded,
        ),
        patch(
            "parcel_shell.sandbox.previews.runner.seed_runner.has_seed",
            lambda _: False,
        ),
    ):
        await runner._render(sandbox_id, factory, MagicMock(), settings)

    async with factory() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        assert row.preview_status == "ready"
        assert row.preview_finished_at is not None
        assert len(row.previews) == 3  # one route × three viewports
        assert all(e["status"] == "ok" for e in row.previews)
    await engine.dispose()


@pytest.mark.asyncio
async def test_render_marks_failed_when_chromium_raises(
    migrations_applied: str, settings, tmp_path: Path
) -> None:
    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    sandbox_id = uuid.uuid4()
    module_root = tmp_path / "sandbox-y"
    module_root.mkdir()

    async with factory() as s:
        s.add(
            SandboxInstall(
                id=sandbox_id,
                name="y",
                version="0.1.0",
                declared_capabilities=[],
                schema_name=f"mod_sandbox_{sandbox_id.hex[:8]}",
                module_root=str(module_root),
                url_prefix="/mod-sandbox/abc",
                gate_report={"passed": True, "findings": []},
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status="active",
                preview_status="pending",
            )
        )
        await s.commit()

    @contextlib.asynccontextmanager
    async def _broken_pw():
        raise RuntimeError("chromium boom")
        yield  # pragma: no cover

    fake_loaded = _make_loaded_module()

    with (
        patch("parcel_shell.sandbox.previews.runner.async_playwright", lambda: _broken_pw()),
        patch(
            "parcel_shell.sandbox.previews.runner.routes.resolve",
            AsyncMock(return_value=["/page"]),
        ),
        patch(
            "parcel_shell.sandbox.previews.runner.sandbox_service.load_sandbox_module",
            lambda *a, **kw: fake_loaded,
        ),
        patch(
            "parcel_shell.sandbox.previews.runner.seed_runner.has_seed",
            lambda _: False,
        ),
    ):
        await runner._render(sandbox_id, factory, MagicMock(), settings)

    async with factory() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        assert row.preview_status == "failed"
        assert row.preview_error and "chromium boom" in row.preview_error
    await engine.dispose()


@pytest.mark.asyncio
async def test_sweep_orphans_flips_rendering_to_failed(
    migrations_applied: str,
) -> None:
    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    sandbox_id = uuid.uuid4()
    async with factory() as s:
        s.add(
            SandboxInstall(
                id=sandbox_id,
                name="z",
                version="0.1.0",
                declared_capabilities=[],
                schema_name=f"mod_sandbox_{sandbox_id.hex[:8]}",
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

    swept = await runner.sweep_orphans(factory)
    assert swept == 1

    async with factory() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        assert row.preview_status == "failed"
        assert row.preview_error == "process_restart"
    await engine.dispose()


@pytest.mark.asyncio
async def test_render_marks_failed_when_no_routes_resolved(
    migrations_applied: str, settings, tmp_path: Path
) -> None:
    """When routes.resolve returns [], the runner marks failed with a clear message."""
    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    sandbox_id = uuid.uuid4()
    schema_name = f"mod_sandbox_{sandbox_id.hex[:8]}"
    module_root = tmp_path / "sandbox-empty"
    module_root.mkdir()

    async with factory() as s:
        s.add(
            SandboxInstall(
                id=sandbox_id, name="empty", version="0.1.0", declared_capabilities=[],
                schema_name=schema_name, module_root=str(module_root),
                url_prefix="/mod-sandbox/abc",
                gate_report={"passed": True, "findings": []},
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=7),
                status="active", preview_status="pending",
            )
        )
        await s.commit()

    captured: list = []
    fake_loaded = _make_loaded_module()

    with patch(
        "parcel_shell.sandbox.previews.runner.async_playwright",
        lambda: _fake_playwright(captured),
    ), patch(
        "parcel_shell.sandbox.previews.runner.routes.resolve",
        AsyncMock(return_value=[]),
    ), patch(
        "parcel_shell.sandbox.previews.runner.sandbox_service.load_sandbox_module",
        lambda *a, **kw: fake_loaded,
    ), patch(
        "parcel_shell.sandbox.previews.runner.seed_runner.has_seed",
        lambda _: False,
    ):
        await runner._render(sandbox_id, factory, MagicMock(), settings)

    async with factory() as s:
        row = await s.get(SandboxInstall, sandbox_id)
        assert row.preview_status == "failed"
        assert row.preview_error == "no routes resolved"
        assert row.previews == []
    await engine.dispose()
