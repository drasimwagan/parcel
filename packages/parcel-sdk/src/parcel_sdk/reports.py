from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ReportContext:
    """Per-request context passed to a report's data function."""

    session: AsyncSession
    user_id: UUID
    params: BaseModel | None


@dataclass(frozen=True, kw_only=True)
class Report:
    """A printable, parameterised report attached to a module manifest."""

    slug: str
    title: str
    permission: str
    template: str
    data: Callable[[ReportContext], Awaitable[dict[str, Any]]]
    params: type[BaseModel] | None = None
    form_template: str | None = None


__all__ = ["Report", "ReportContext"]
