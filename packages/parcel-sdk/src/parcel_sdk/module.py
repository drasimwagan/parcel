from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter  # noqa: F401
    from sqlalchemy import MetaData  # noqa: F401

    from parcel_sdk.dashboards import Dashboard
    from parcel_sdk.previews import PreviewRoute
    from parcel_sdk.reports import Report
    from parcel_sdk.workflows import Workflow, WorkflowContext

from parcel_sdk.sidebar import SidebarItem


@dataclass(frozen=True)
class Permission:
    name: str
    description: str


@dataclass(frozen=True)
class Module:
    name: str
    version: str
    permissions: tuple[Permission, ...] = ()
    capabilities: tuple[str, ...] = ()
    alembic_ini: Path | None = None
    metadata: MetaData | None = None
    # Phase 5 additions — optional UI contribution:
    router: Any | None = None
    templates_dir: Path | None = None
    sidebar_items: tuple[SidebarItem, ...] = ()
    dashboards: tuple[Dashboard, ...] = ()
    reports: tuple[Report, ...] = ()
    workflows: tuple[Workflow, ...] = ()
    # Phase 10c — async functions invoked by RunModuleFunction action.
    workflow_functions: dict[str, Callable[[WorkflowContext], Awaitable[Any]]] = field(
        default_factory=dict
    )
    # Phase 11 — optional declared-routes override for the sandbox preview
    # renderer. When empty (the default), the renderer auto-walks
    # `module.router.routes`.
    preview_routes: tuple[PreviewRoute, ...] = ()
