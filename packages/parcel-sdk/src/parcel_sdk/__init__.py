"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 9 surface: Phase 8 + reports (Report, ReportContext).
"""

from __future__ import annotations

from parcel_sdk import shell_api
from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.dashboards import (
    BarWidget,
    Ctx,
    Dashboard,
    Dataset,
    HeadlineWidget,
    Kpi,
    KpiWidget,
    LineWidget,
    Series,
    Table,
    TableWidget,
    Widget,
    scalar_query,
    series_query,
    table_query,
)
from parcel_sdk.module import Module, Permission
from parcel_sdk.reports import Report, ReportContext
from parcel_sdk.sidebar import SidebarItem

__all__ = [
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Module",
    "Permission",
    "Report",
    "ReportContext",
    "Series",
    "SidebarItem",
    "Table",
    "TableWidget",
    "Widget",
    "__version__",
    "run_async_migrations",
    "scalar_query",
    "series_query",
    "shell_api",
    "table_query",
]
__version__ = "0.5.0"
