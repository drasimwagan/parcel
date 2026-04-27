"""Preview-route declarations for sandbox screenshot rendering (Phase 11)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, kw_only=True)
class PreviewRoute:
    """A single route the sandbox preview renderer should screenshot.

    `path` is the route the module's APIRouter mounts (with `{name}` placeholders
    where applicable). `title` is an optional caption for the UI; falls back to
    `path`. `params` is an optional async resolver that returns a dict of
    placeholder substitutions — `{"id": "<seeded-uuid>"}` is the canonical case.
    """

    path: str
    title: str | None = None
    params: Callable[[AsyncSession], Awaitable[dict[str, str]]] | None = None
