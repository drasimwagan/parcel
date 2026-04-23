from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.db import get_session
from parcel_shell.modules import service as module_service
from parcel_shell.modules.discovery import DiscoveredModule, discover_modules
from parcel_shell.modules.models import InstalledModule
from parcel_shell.modules.schemas import ModuleSummary
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": visible_sections(perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


def _discovered_index() -> dict[str, DiscoveredModule]:
    return {d.module.name: d for d in discover_modules()}


def _summary(name: str, row: InstalledModule | None, d: DiscoveredModule | None) -> ModuleSummary:
    declared = list(d.module.capabilities) if d is not None else []
    installed_ver = row.version if row else (d.module.version if d else "")
    return ModuleSummary(
        name=name,
        version=installed_ver,
        is_active=(row.is_active if row is not None else None),
        is_discoverable=(d is not None),
        declared_capabilities=sorted(declared),
        approved_capabilities=(list(row.capabilities) if row else []),
        schema_name=(row.schema_name if row else None),
        installed_at=(row.installed_at if row else None),
        last_migrated_at=(row.last_migrated_at if row else None),
        last_migrated_rev=(row.last_migrated_rev if row else None),
    )


@router.get("/modules", response_class=HTMLResponse)
async def modules_list(
    request: Request,
    user=Depends(html_require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    rows = (await db.execute(select(InstalledModule))).scalars().all()
    by_name = {r.name: r for r in rows}
    names = sorted(set(index) | set(by_name))
    modules = [_summary(n, by_name.get(n), index.get(n)) for n in names]
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "modules/list.html",
        {**(await _ctx(request, user, db, "/modules")), "modules": modules},
    )


@router.get("/modules/{name}", response_class=HTMLResponse)
async def modules_detail(
    name: str,
    request: Request,
    user=Depends(html_require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    row = await db.get(InstalledModule, name)
    if row is None and name not in index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found")
    summary = _summary(name, row, index.get(name))
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "modules/detail.html",
        {**(await _ctx(request, user, db, "/modules")), "summary": summary},
    )


@router.post("/modules/install")
async def modules_install(
    request: Request,
    name: str = Form(...),
    user=Depends(html_require_permission("modules.install")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    form = await request.form()
    approved: list[str] = [v for v in form.getlist("approve_capabilities") if isinstance(v, str)]
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.install_module(
            db,
            name=name,
            approve_capabilities=approved,
            discovered=index,
            database_url=database_url,
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_discovered") from None
    except module_service.ModuleAlreadyInstalled:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg="Already installed."),
            secret=request.app.state.settings.session_secret,
        )
        return response
    except module_service.CapabilityMismatch:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg="Approve all declared capabilities to install."),
            secret=request.app.state.settings.session_secret,
        )
        return response
    except module_service.ModuleMigrationFailed as e:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg=f"Install failed: {e}"),
            secret=request.app.state.settings.session_secret,
        )
        return response
    response = RedirectResponse(url=f"/modules/{name}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Installed {name}."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/modules/{name}/upgrade")
async def modules_upgrade(
    name: str,
    request: Request,
    user=Depends(html_require_permission("modules.upgrade")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.upgrade_module(
            db, name=name, discovered=index, database_url=database_url
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from None
    except module_service.ModuleMigrationFailed as e:
        response = RedirectResponse(url=f"/modules/{name}", status_code=303)
        set_flash(
            response,
            Flash(kind="error", msg=f"Upgrade failed: {e}"),
            secret=request.app.state.settings.session_secret,
        )
        return response
    response = RedirectResponse(url=f"/modules/{name}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"{name} migrated to head."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/modules/{name}/uninstall")
async def modules_uninstall(
    name: str,
    request: Request,
    drop_data: bool = Query(default=False),
    user=Depends(html_require_permission("modules.uninstall")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await module_service.uninstall_module(
            db,
            name=name,
            drop_data=drop_data,
            discovered=index,
            database_url=database_url,
        )
    except module_service.ModuleNotDiscovered:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from None
    response = RedirectResponse(url="/modules", status_code=303)
    msg = f"{name} uninstalled" + (" and data dropped" if drop_data else " (soft)") + "."
    set_flash(
        response,
        Flash(kind="success", msg=msg),
        secret=request.app.state.settings.session_secret,
    )
    return response
