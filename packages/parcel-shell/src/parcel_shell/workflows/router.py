from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_sdk import Manual
from parcel_sdk.shell_api import Flash
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.registry import collect_workflows, find_workflow
from parcel_shell.workflows.runner import run_workflow

_log = structlog.get_logger("parcel_shell.workflows.router")

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _group_by_module(registered, perms):
    groups: dict[str, list] = {}
    for r in registered:
        if r.workflow.permission in perms:
            groups.setdefault(r.module_name, []).append(r.workflow)
    return sorted(groups.items())


@router.get("", response_class=HTMLResponse)
async def workflows_list(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    groups = _group_by_module(registered, perms)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "workflows/list.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/workflows",
            "settings": request.app.state.settings,
            "permissions": perms,
            "groups": groups,
        },
    )


@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def workflow_detail(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None or hit.workflow.permission not in perms:
        raise _not_found()

    audits = (
        await db.scalars(
            select(WorkflowAudit)
            .where(
                WorkflowAudit.module == module_name,
                WorkflowAudit.workflow_slug == slug,
            )
            .order_by(desc(WorkflowAudit.created_at))
            .limit(50)
        )
    ).all()

    has_manual = any(isinstance(t, Manual) for t in hit.workflow.triggers)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "workflows/detail.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/workflows",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "workflow": hit.workflow,
            "audits": audits,
            "has_manual_trigger": has_manual,
        },
    )


@router.post("/{module_name}/{slug}/run")
async def workflow_run(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None or hit.workflow.permission not in perms:
        raise _not_found()

    manual_triggers = [t for t in hit.workflow.triggers if isinstance(t, Manual)]
    if not manual_triggers:
        raise _not_found()

    sessionmaker = request.app.state.sessionmaker
    synthetic_event = manual_triggers[0].event
    # Manual triggers bypass `_matches` (which returns False for them by design).
    # Run the workflow chain directly with a synthetic event.
    await run_workflow(
        module_name,
        hit.workflow,
        {"event": synthetic_event, "subject": None, "subject_id": None, "changed": ()},
        sessionmaker,
    )

    response = RedirectResponse(f"/workflows/{module_name}/{slug}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Manually triggered {hit.workflow.title!r}."),
        secret=request.app.state.settings.session_secret,
    )
    return response
