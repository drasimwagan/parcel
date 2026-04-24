from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from parcel_sdk.dashboards import (
    BarWidget,
    Ctx,
    Dashboard,
    HeadlineWidget,
    KpiWidget,
    LineWidget,
    TableWidget,
)
from parcel_shell.dashboards.registry import (
    RegisteredDashboard,
    collect_dashboards,
    find_dashboard,
)
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

_log = structlog.get_logger("parcel_shell.dashboards")

router = APIRouter(prefix="/dashboards", tags=["dashboards"])

_PARTIALS = {
    KpiWidget: "dashboards/_widget_kpi.html",
    LineWidget: "dashboards/_widget_line.html",
    BarWidget: "dashboards/_widget_bar.html",
    TableWidget: "dashboards/_widget_table.html",
    HeadlineWidget: "dashboards/_widget_headline.html",
}


def _group_by_module(
    registered: list[RegisteredDashboard], perms: set[str]
) -> list[tuple[str, list[Dashboard]]]:
    groups: dict[str, list[Dashboard]] = {}
    for r in registered:
        if r.dashboard.permission in perms:
            groups.setdefault(r.module_name, []).append(r.dashboard)
    return sorted(groups.items())


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


@router.get("", response_class=HTMLResponse)
async def dashboards_list(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    groups = _group_by_module(registered, perms)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboards/list.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/dashboards",
            "settings": request.app.state.settings,
            "permissions": perms,
            "groups": groups,
        },
    )


@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def dashboard_detail(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    hit = find_dashboard(registered, module_name, slug)
    if hit is None or hit.dashboard.permission not in perms:
        raise _not_found()
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboards/detail.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/dashboards",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "dashboard": hit.dashboard,
        },
    )


@router.get("/{module_name}/{slug}/widgets/{widget_id}", response_class=HTMLResponse)
async def dashboard_widget(
    module_name: str,
    slug: str,
    widget_id: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_dashboards(request.app)
    hit = find_dashboard(registered, module_name, slug)
    if hit is None or hit.dashboard.permission not in perms:
        raise _not_found()
    widget = next((w for w in hit.dashboard.widgets if w.id == widget_id), None)
    if widget is None:
        raise _not_found()

    templates = get_templates()
    template_name = _PARTIALS[type(widget)]

    if isinstance(widget, HeadlineWidget):
        return templates.TemplateResponse(request, template_name, {"widget": widget})

    try:
        data = await widget.data(Ctx(session=db, user_id=user.id))
        return templates.TemplateResponse(request, template_name, {"widget": widget, "data": data})
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "dashboards.widget.failed",
            module=module_name,
            slug=slug,
            widget=widget_id,
            error=str(exc),
        )
        return templates.TemplateResponse(
            request, "dashboards/_widget_error.html", {"widget": widget}
        )
