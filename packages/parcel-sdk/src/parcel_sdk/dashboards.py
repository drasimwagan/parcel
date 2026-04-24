from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Ctx:
    """Per-request context passed to widget data functions."""

    session: AsyncSession
    user_id: UUID


@dataclass(frozen=True)
class Dataset:
    label: str
    values: list[float | int]


@dataclass(frozen=True)
class Series:
    labels: list[str]
    datasets: list[Dataset]


@dataclass(frozen=True)
class Kpi:
    value: str | int | float
    delta: float | None = None
    delta_label: str | None = None


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[list[Any]]


@dataclass(frozen=True)
class Widget:
    """Base widget. Subclasses add a type-specific `data` field."""

    id: str
    title: str
    col_span: int = 2


@dataclass(frozen=True, kw_only=True)
class KpiWidget(Widget):
    data: Callable[[Ctx], Awaitable[Kpi]]


@dataclass(frozen=True, kw_only=True)
class LineWidget(Widget):
    data: Callable[[Ctx], Awaitable[Series]]


@dataclass(frozen=True, kw_only=True)
class BarWidget(Widget):
    data: Callable[[Ctx], Awaitable[Series]]


@dataclass(frozen=True, kw_only=True)
class TableWidget(Widget):
    data: Callable[[Ctx], Awaitable[Table]]


@dataclass(frozen=True)
class HeadlineWidget(Widget):
    text: str = ""
    href: str | None = None


@dataclass(frozen=True)
class Dashboard:
    name: str
    slug: str
    title: str
    permission: str
    widgets: tuple[Widget, ...]
    description: str = ""


__all__ = [
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Series",
    "Table",
    "TableWidget",
    "Widget",
]
