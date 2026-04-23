from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis_async
import structlog
from fastapi import FastAPI

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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(env=settings.env, level=settings.log_level)
    log = structlog.get_logger("parcel_shell")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        sessionmaker = create_sessionmaker(engine)
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.redis = redis_async.from_url(settings.redis_url, decode_responses=True)
        app.state.settings = settings

        # Upsert the in-memory permission registry into the DB. Phase 2 is a no-op
        # (the 0002 migration seeded these rows); the hook exists so Phase 3 modules
        # can register permissions that land here at boot.
        async with sessionmaker() as s:
            await permission_registry.sync_to_db(s)
            await s.commit()

        # Flip previously-installed modules whose package is no longer
        # entry-point-discoverable to is_active=false.
        async with sessionmaker() as s:
            await module_service.sync_on_boot(s)
            await s.commit()

        log.info("shell.startup", env=settings.env)
        try:
            yield
        finally:
            await app.state.redis.aclose()
            await engine.dispose()
            log.info("shell.shutdown")

    app = FastAPI(title="Parcel Shell", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(modules_router)

    return app
