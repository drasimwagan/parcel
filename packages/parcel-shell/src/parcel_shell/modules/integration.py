from __future__ import annotations

import structlog
from fastapi import FastAPI

from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.ui.templates import add_template_dir

_log = structlog.get_logger("parcel_shell.modules.integration")


def _ensure_state(app: FastAPI) -> None:
    if not hasattr(app.state, "active_modules"):
        app.state.active_modules = set()
    if not hasattr(app.state, "active_modules_sidebar"):
        app.state.active_modules_sidebar = {}
    if not hasattr(app.state, "active_modules_manifest"):
        app.state.active_modules_manifest = {}


def mount_module(app: FastAPI, discovered: DiscoveredModule) -> None:
    """Mount a module's router, templates, and sidebar onto the live app.

    Idempotent: calling twice with the same module is a no-op.
    """
    _ensure_state(app)
    name = discovered.module.name
    if name in app.state.active_modules:
        return

    if discovered.module.router is not None:
        app.include_router(discovered.module.router, prefix=f"/mod/{name}")
    if discovered.module.templates_dir is not None:
        add_template_dir(discovered.module.templates_dir)

    app.state.active_modules.add(name)
    app.state.active_modules_sidebar[name] = tuple(discovered.module.sidebar_items)
    app.state.active_modules_manifest[name] = discovered.module
    _log.info("module.mounted", name=name)

    declared = {p.name for p in discovered.module.permissions}
    for report in getattr(discovered.module, "reports", ()):
        if report.permission not in declared:
            _log.warning(
                "module.report.unknown_permission",
                module=name,
                slug=report.slug,
                permission=report.permission,
            )
    for workflow in getattr(discovered.module, "workflows", ()):
        if workflow.permission not in declared:
            _log.warning(
                "module.workflow.unknown_permission",
                module=name,
                slug=workflow.slug,
                permission=workflow.permission,
            )

    # Phase 10c — capability checks per action.
    declared_caps = set(getattr(discovered.module, "capabilities", ()))
    for workflow in getattr(discovered.module, "workflows", ()):
        for action in workflow.actions:
            cap = getattr(type(action), "_required_capability", None)
            if cap and cap not in declared_caps:
                _log.warning(
                    "module.workflow.missing_capability",
                    module=name,
                    slug=workflow.slug,
                    action=type(action).__name__,
                    capability=cap,
                )


async def sync_active_modules(app: FastAPI) -> None:
    """At lifespan startup, mount every active installed module."""
    from sqlalchemy import select

    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    _ensure_state(app)
    sessionmaker = app.state.sessionmaker
    discovered = {d.module.name: d for d in discover_modules()}
    async with sessionmaker() as s:
        rows = (
            (await s.execute(select(InstalledModule).where(InstalledModule.is_active.is_(True))))
            .scalars()
            .all()
        )
    for row in rows:
        d = discovered.get(row.name)
        if d is None:
            continue
        mount_module(app, d)
