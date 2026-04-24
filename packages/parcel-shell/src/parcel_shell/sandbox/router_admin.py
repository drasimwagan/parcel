from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.auth.dependencies import require_permission
from parcel_shell.db import get_session
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall
from parcel_shell.sandbox.schemas import PromoteIn, SandboxOut

router = APIRouter(prefix="/admin/sandbox", tags=["admin", "sandbox"])


def _to_out(row: SandboxInstall) -> SandboxOut:
    return SandboxOut.model_validate(row)


@router.get("", response_model=list[SandboxOut])
async def list_sandboxes(
    _: object = Depends(require_permission("sandbox.read")),
    db: AsyncSession = Depends(get_session),
) -> list[SandboxOut]:
    rows = (
        (
            await db.execute(
                select(SandboxInstall).order_by(SandboxInstall.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_to_out(r) for r in rows]


@router.get("/{sandbox_id}", response_model=SandboxOut)
async def get_sandbox(
    sandbox_id: UUID,
    _: object = Depends(require_permission("sandbox.read")),
    db: AsyncSession = Depends(get_session),
) -> SandboxOut:
    row = await db.get(SandboxInstall, sandbox_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found")
    return _to_out(row)


@router.post("", response_model=SandboxOut, status_code=status.HTTP_201_CREATED)
async def create_sandbox_endpoint(
    request: Request,
    file: UploadFile | None = None,
    _: object = Depends(require_permission("sandbox.install")),
    db: AsyncSession = Depends(get_session),
) -> SandboxOut:
    settings = request.app.state.settings
    source_zip_bytes: bytes | None = None
    source_dir: Path | None = None
    if file is not None:
        source_zip_bytes = await file.read()
    else:
        try:
            body = await request.json()
        except Exception:
            body = None
        if not body or "path" not in body:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "provide either multipart 'file' or JSON {'path': ...}",
            )
        source_dir = Path(body["path"])
        if not source_dir.exists() or not source_dir.is_dir():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"path not a directory: {source_dir}")

    try:
        row = await sandbox_service.create_sandbox(
            db,
            source_zip_bytes=source_zip_bytes,
            source_dir=source_dir,
            app=request.app,
            settings=settings,
        )
    except sandbox_service.GateRejected as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"gate_report": exc.report.to_dict()},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _to_out(row)


@router.post("/{sandbox_id}/promote", response_model=dict, status_code=status.HTTP_201_CREATED)
async def promote_sandbox_endpoint(
    sandbox_id: UUID,
    body: PromoteIn,
    request: Request,
    _: object = Depends(require_permission("sandbox.promote")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    settings = request.app.state.settings
    try:
        installed = await sandbox_service.promote_sandbox(
            db,
            sandbox_id,
            target_name=body.name,
            approve_capabilities=body.approve_capabilities,
            app=request.app,
            settings=settings,
        )
    except sandbox_service.SandboxNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found") from exc
    except sandbox_service.TargetNameTaken as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"name taken: {body.name}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"name": installed.name, "version": installed.version}


@router.delete("/{sandbox_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_sandbox_endpoint(
    sandbox_id: UUID,
    request: Request,
    _: object = Depends(require_permission("sandbox.install")),
    db: AsyncSession = Depends(get_session),
) -> None:
    try:
        await sandbox_service.dismiss_sandbox(db, sandbox_id, request.app)
    except sandbox_service.SandboxNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sandbox_not_found") from exc
