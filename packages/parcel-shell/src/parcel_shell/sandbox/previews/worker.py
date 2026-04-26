"""ARQ-registered job function for sandbox preview rendering."""

from __future__ import annotations

import uuid

from parcel_shell.config import get_settings
from parcel_shell.sandbox.previews.runner import _render


async def render_sandbox_previews(ctx: dict, sandbox_id: str) -> None:
    """Worker entry point — delegates to the shared `_render` coroutine."""
    sessionmaker = ctx["sessionmaker"]
    app = ctx["app"]
    settings = get_settings()
    await _render(uuid.UUID(sandbox_id), sessionmaker, app, settings)
