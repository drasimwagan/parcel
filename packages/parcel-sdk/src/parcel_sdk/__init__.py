"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 11 surface: Phase 10c + PreviewRoute for sandbox screenshot rendering.
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
from parcel_sdk.previews import PreviewRoute
from parcel_sdk.reports import Report, ReportContext
from parcel_sdk.sidebar import SidebarItem
from parcel_sdk.workflows import (
    Action,
    CallWebhook,
    EmitAudit,
    GenerateReport,
    Manual,
    OnCreate,
    OnSchedule,
    OnUpdate,
    RunModuleFunction,
    SendEmail,
    Trigger,
    UpdateField,
    Workflow,
    WorkflowContext,
)

__all__ = [
    "Action",
    "BarWidget",
    "CallWebhook",
    "Ctx",
    "Dashboard",
    "Dataset",
    "EmitAudit",
    "GenerateReport",
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
    "PreviewRoute",
    "Report",
    "ReportContext",
    "RunModuleFunction",
    "SendEmail",
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
__version__ = "0.10.0"
