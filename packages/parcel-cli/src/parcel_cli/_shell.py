"""Helpers for CLI commands that need a booted shell.

Commands like ``parcel install`` and ``parcel migrate`` reuse the shell's
service layer directly rather than going through HTTP. Wrapping
:func:`parcel_shell.app.create_app` in :class:`asgi_lifespan.LifespanManager`
runs the full startup path (DB engine, sessionmaker, module discovery,
``sync_active_modules``) without binding a TCP port.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from asgi_lifespan import LifespanManager
from fastapi import FastAPI


@asynccontextmanager
async def with_shell() -> AsyncIterator[FastAPI]:
    from parcel_shell.app import create_app

    app = create_app()
    async with LifespanManager(app):
        yield app
