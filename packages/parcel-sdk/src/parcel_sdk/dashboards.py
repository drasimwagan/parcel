from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import text

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


# kw_only=True on data-bearing subclasses: keeps `data` required despite
# Widget.col_span having a default. Without it, dataclass inheritance rejects
# a non-default field after a defaulted one.
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


async def scalar_query(session: AsyncSession, sql: str, **params: Any) -> Any:
    """Return the first column of the first row, or None if empty.

    Params are bound via SQLAlchemy parameterisation — never string-interpolate.
    """
    result = await session.execute(text(sql), params)
    row = result.first()
    if row is None:
        return None
    return row[0]


async def series_query(
    session: AsyncSession,
    sql: str,
    label_col: str,
    value_col: str,
    **params: Any,
) -> Series:
    """Shape a query result into a single-dataset ``Series``.

    Values are coerced to float to match ``Dataset.values`` (Postgres `numeric`
    columns return Decimal by default; Chart.js expects plain numbers).
    """
    result = await session.execute(text(sql), params)
    rows = result.mappings().all()
    labels = [str(r[label_col]) for r in rows]
    values: list[float | int] = [
        float(r[value_col]) if r[value_col] is not None else 0.0 for r in rows
    ]
    return Series(labels=labels, datasets=[Dataset(label=value_col, values=values)])


async def table_query(session: AsyncSession, sql: str, **params: Any) -> Table:
    """Shape a query result into a ``Table`` using column order."""
    result = await session.execute(text(sql), params)
    columns = list(result.keys())
    return Table(columns=columns, rows=[list(r) for r in result.all()])


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
    "scalar_query",
    "series_query",
    "table_query",
]
