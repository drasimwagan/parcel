from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.db import get_session
from parcel_shell.rbac import service as rbac_service
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await rbac_service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": sidebar_for(request, perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


def _flash(request: Request, response: Response, kind: str, msg: str) -> None:
    set_flash(
        response,
        Flash(kind=kind, msg=msg),  # type: ignore[arg-type]
        secret=request.app.state.settings.session_secret,
    )


@router.get("/sandbox", response_class=HTMLResponse)
async def sandbox_list(
    request: Request,
    user=Depends(html_require_permission("sandbox.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    rows = (
        (await db.execute(select(SandboxInstall).order_by(SandboxInstall.created_at.desc())))
        .scalars()
        .all()
    )
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "sandbox/list.html",
        {**(await _ctx(request, user, db, "/sandbox")), "sandboxes": rows},
    )


@router.get("/sandbox/new", response_class=HTMLResponse)
async def sandbox_new_form(
    request: Request,
    user=Depends(html_require_permission("sandbox.install")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "sandbox/new.html",
        await _ctx(request, user, db, "/sandbox"),
    )


@router.post("/sandbox")
async def sandbox_upload(
    request: Request,
    file: UploadFile,
    user=Depends(html_require_permission("sandbox.install")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        blob = await file.read()
        row = await sandbox_service.create_sandbox(
            db,
            source_zip_bytes=blob,
            app=request.app,
            settings=request.app.state.settings,
        )
    except sandbox_service.GateRejected as exc:
        response = RedirectResponse(url="/sandbox", status_code=303)
        _flash(
            request,
            response,
            "error",
            f"Gate rejected: {len(exc.report.errors)} errors",
        )
        return response
    except ValueError as exc:
        response = RedirectResponse(url="/sandbox/new", status_code=303)
        _flash(request, response, "error", str(exc))
        return response
    response = RedirectResponse(url=f"/sandbox/{row.id}", status_code=303)
    _flash(request, response, "success", f"Sandbox {row.name} installed.")
    return response


@router.get("/sandbox/{sandbox_id}", response_class=HTMLResponse)
async def sandbox_detail(
    sandbox_id: UUID,
    request: Request,
    user=Depends(html_require_permission("sandbox.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    row = await db.get(SandboxInstall, sandbox_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found")
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "sandbox/detail.html",
        {**(await _ctx(request, user, db, "/sandbox")), "sb": row},
    )


@router.post("/sandbox/{sandbox_id}/dismiss")
async def sandbox_dismiss(
    sandbox_id: UUID,
    request: Request,
    user=Depends(html_require_permission("sandbox.install")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await sandbox_service.dismiss_sandbox(db, sandbox_id, request.app)
    except sandbox_service.SandboxNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found") from exc
    response = RedirectResponse(url="/sandbox", status_code=303)
    _flash(request, response, "info", "Sandbox dismissed.")
    return response


@router.post("/sandbox/{sandbox_id}/promote")
async def sandbox_promote(
    sandbox_id: UUID,
    request: Request,
    name: str = Form(...),
    user=Depends(html_require_permission("sandbox.promote")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    form = await request.form()
    approved = [v for v in form.getlist("approve_capabilities") if isinstance(v, str)]
    try:
        await sandbox_service.promote_sandbox(
            db,
            sandbox_id,
            target_name=name,
            approve_capabilities=approved,
            app=request.app,
            settings=request.app.state.settings,
        )
    except sandbox_service.SandboxNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found") from exc
    except sandbox_service.TargetNameTaken:
        response = RedirectResponse(url=f"/sandbox/{sandbox_id}", status_code=303)
        _flash(request, response, "error", f"Name {name!r} is already taken.")
        return response
    except ValueError as exc:
        response = RedirectResponse(url=f"/sandbox/{sandbox_id}", status_code=303)
        _flash(request, response, "error", str(exc))
        return response
    response = RedirectResponse(url=f"/modules/{name}", status_code=303)
    _flash(request, response, "success", f"Promoted to module {name!r}.")
    return response
