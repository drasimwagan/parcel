from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.dependencies import require_permission
from parcel_shell.db import get_session
from parcel_shell.modules import service
from parcel_shell.modules.discovery import DiscoveredModule, discover_modules
from parcel_shell.modules.models import InstalledModule
from parcel_shell.modules.schemas import InstallModuleRequest, ModuleSummary

router = APIRouter(prefix="/admin/modules", tags=["admin", "modules"])


def _discovered_index() -> dict[str, DiscoveredModule]:
    return {d.module.name: d for d in discover_modules()}


def _summary(
    name: str,
    row: InstalledModule | None,
    d: DiscoveredModule | None,
) -> ModuleSummary:
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


@router.get("", response_model=list[ModuleSummary])
async def list_modules(
    _: object = Depends(require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> list[ModuleSummary]:
    index = _discovered_index()
    rows = (await db.execute(select(InstalledModule))).scalars().all()
    by_name = {r.name: r for r in rows}
    names = sorted(set(index) | set(by_name))
    return [_summary(n, by_name.get(n), index.get(n)) for n in names]


@router.get("/{name}", response_model=ModuleSummary)
async def get_module(
    name: str,
    _: object = Depends(require_permission("modules.read")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    row = await db.get(InstalledModule, name)
    if row is None and name not in index:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found")
    return _summary(name, row, index.get(name))


@router.post("/install", response_model=ModuleSummary, status_code=201)
async def install(
    payload: InstallModuleRequest,
    request: Request,
    _: object = Depends(require_permission("modules.install")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        row = await service.install_module(
            db,
            name=payload.name,
            approve_capabilities=payload.approve_capabilities,
            discovered=index,
            database_url=database_url,
            app=request.app,
        )
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_discovered") from e
    except service.ModuleAlreadyInstalled as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "module_already_installed") from e
    except service.CapabilityMismatch as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "capability_mismatch") from e
    except service.ModuleMigrationFailed as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "module_install_failed") from e
    return _summary(row.name, row, index.get(row.name))


@router.post("/{name}/upgrade", response_model=ModuleSummary)
async def upgrade(
    name: str,
    request: Request,
    _: object = Depends(require_permission("modules.upgrade")),
    db: AsyncSession = Depends(get_session),
) -> ModuleSummary:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        row = await service.upgrade_module(
            db, name=name, discovered=index, database_url=database_url
        )
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from e
    except service.ModuleMigrationFailed as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "module_upgrade_failed") from e
    return _summary(row.name, row, index.get(row.name))


@router.post("/{name}/uninstall", status_code=204)
async def uninstall(
    name: str,
    request: Request,
    drop_data: bool = Query(default=False),
    _: object = Depends(require_permission("modules.uninstall")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    index = _discovered_index()
    database_url = request.app.state.settings.database_url
    try:
        await service.uninstall_module(
            db,
            name=name,
            drop_data=drop_data,
            discovered=index,
            database_url=database_url,
        )
    except service.ModuleNotDiscovered as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module_not_found") from e
    return Response(status_code=204)
