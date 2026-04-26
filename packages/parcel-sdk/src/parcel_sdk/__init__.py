"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 10b-retry surface: Phase 10b + per-workflow retry semantics.
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
from parcel_sdk.workflows import (
    Action,
    EmitAudit,
    Manual,
    OnCreate,
    OnSchedule,
    OnUpdate,
    Trigger,
    UpdateField,
    Workflow,
    WorkflowContext,
)

__all__ = [
    "Action",
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "EmitAudit",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Manual",
    "Module",
    "OnCreate",
    "OnSchedule",
    "OnUpdate",
    "Permission",
    "Report",
    "ReportContext",
    "Series",
    "SidebarItem",
    "Table",
    "TableWidget",
    "Trigger",
    "UpdateField",
    "Widget",
    "Workflow",
    "WorkflowContext",
    "__version__",
    "run_async_migrations",
    "scalar_query",
    "series_query",
    "shell_api",
    "table_query",
]
__version__ = "0.8.0"
