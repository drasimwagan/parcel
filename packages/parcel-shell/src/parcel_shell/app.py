from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import RedirectResponse

from parcel_shell.auth.router import router as auth_router
from parcel_shell.config import Settings, get_settings
from parcel_shell.db import create_engine, create_sessionmaker
from parcel_shell.health import router as health_router
from parcel_shell.logging import configure_logging
from parcel_shell.middleware import RequestIdMiddleware
from parcel_shell.modules import service as module_service
from parcel_shell.modules.router_admin import router as modules_router
from parcel_shell.rbac.registry import registry as permission_registry
from parcel_shell.rbac.router_admin import router as admin_router
from parcel_shell.ui.dependencies import HTMLRedirect, set_flash
from parcel_shell.ui.middleware import FlashMiddleware

_UI_STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(env=settings.env, level=settings.log_level)
    log = structlog.get_logger("parcel_shell")

    from parcel_sdk import shell_api as _sdk_shell_api
    from parcel_shell.shell_api_impl import DefaultShellBinding

    _sdk_shell_api.bind(DefaultShellBinding(settings), force=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        sessionmaker = create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        app.state.settings = settings

        # ARQ pool for workflow dispatch (Phase 10b). Optional at boot —
        # tests use fake Redis URLs and inline-mode short-circuits dispatch
        # before this is consulted, so a failure here shouldn't block the shell.
        # `conn_retries=1` skips the default 5-retry backoff that would
        # exceed test-lifespan timeouts.
        from arq import create_pool
        from arq.connections import RedisSettings

        rs = RedisSettings.from_dsn(settings.redis_url)
        rs.conn_retries = 1
        try:
            app.state.arq_redis = await create_pool(rs)
        except Exception as exc:  # noqa: BLE001
            app.state.arq_redis = None
            log.warning("workflows.arq_pool.unavailable", reason=str(exc))

        from parcel_shell.ai.provider import build_provider

        try:
            app.state.ai_provider = build_provider(settings)
        except ValueError as exc:
            app.state.ai_provider = None
            log.warning("ai.provider.not_configured", reason=str(exc))

        async with sessionmaker() as s:
            await permission_registry.sync_to_db(s)
            await s.commit()

        async with sessionmaker() as s:
            await module_service.sync_on_boot(s)
            await s.commit()

        from parcel_shell.modules.integration import sync_active_modules
        from parcel_shell.sandbox.service import mount_sandbox_on_boot

        await sync_active_modules(app)

        # Workflows: install the after-commit listener and tell the runner
        # which app is live (so dispatch can read app.state.active_modules_manifest).
        from parcel_shell.workflows.bus import install_after_commit_listener
        from parcel_shell.workflows.runner import set_active_app

        install_after_commit_listener()
        set_active_app(app)

        async with sessionmaker() as s:
            await mount_sandbox_on_boot(s, app)

        from parcel_shell.ai.chat import service as chat_service

        async with sessionmaker() as s:
            swept = await chat_service.sweep_orphans(s)
            await s.commit()
            if swept:
                log.warning("ai.chat.orphans_swept", count=swept)

        app.state.ai_tasks = set()
        app.state.preview_tasks = set()

        # Phase 11 — orphan sweep mirrors the AI chat sweep.
        from parcel_shell.sandbox.previews.runner import sweep_orphans

        swept_previews = await sweep_orphans(sessionmaker)
        if swept_previews:
            log.warning("sandbox.preview.orphans_swept", count=swept_previews)

        log.info("shell.startup", env=settings.env)
        try:
            yield
        finally:
            import asyncio as _asyncio

            tasks = list(getattr(app.state, "ai_tasks", set()))
            for t in tasks:
                t.cancel()
            if tasks:
                await _asyncio.gather(*tasks, return_exceptions=True)

            preview_tasks = list(getattr(app.state, "preview_tasks", set()))
            for t in preview_tasks:
                t.cancel()
            if preview_tasks:
                await _asyncio.gather(*preview_tasks, return_exceptions=True)
            if getattr(app.state, "arq_redis", None) is not None:
                await app.state.arq_redis.close()
            await app.state.redis.aclose()
            await engine.dispose()
            log.info("shell.shutdown")

    app = FastAPI(title="Parcel Shell", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(FlashMiddleware)

    # Static assets for the UI.
    app.mount("/static", StaticFiles(directory=str(_UI_STATIC_DIR)), name="static")

    # JSON APIs (Phases 1-3).
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(modules_router)

    from parcel_shell.sandbox.router_admin import router as sandbox_admin_router

    app.include_router(sandbox_admin_router)

    from parcel_shell.ai.router_admin import router as ai_admin_router

    app.include_router(ai_admin_router)

    # HTML UI (Phase 4). Lazy imports keep this resilient if a router fails to load.
    from parcel_shell.ui.routes.auth import router as ui_auth_router
    from parcel_shell.ui.routes.dashboard import router as ui_dashboard_router
    from parcel_shell.ui.routes.modules import router as ui_modules_router
    from parcel_shell.ui.routes.roles import router as ui_roles_router
    from parcel_shell.ui.routes.users import router as ui_users_router

    app.include_router(ui_auth_router)
    app.include_router(ui_dashboard_router)
    app.include_router(ui_users_router)
    app.include_router(ui_roles_router)
    app.include_router(ui_modules_router)

    from parcel_shell.sandbox.router_ui import router as ui_sandbox_router

    app.include_router(ui_sandbox_router)

    from parcel_shell.ai.chat.router_ui import router as ai_chat_ui_router

    app.include_router(ai_chat_ui_router)

    from parcel_shell.dashboards.router import router as dashboards_router

    app.include_router(dashboards_router)

    from parcel_shell.reports.router import router as reports_router

    app.include_router(reports_router)

    from parcel_shell.workflows.router import router as workflows_router

    app.include_router(workflows_router)

    @app.exception_handler(HTMLRedirect)
    async def _html_redirect(request: Request, exc: HTMLRedirect) -> RedirectResponse:
        response = RedirectResponse(url=exc.location, status_code=303)
        if exc.flash is not None:
            set_flash(response, exc.flash, secret=settings.session_secret)
        return response

    return app
