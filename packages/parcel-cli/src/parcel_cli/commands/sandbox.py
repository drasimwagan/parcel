"""`parcel sandbox` subcommand group."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import typer

from parcel_cli._shell import with_shell

app = typer.Typer(
    name="sandbox",
    help="Parcel sandbox — gated installs at mod_sandbox_<uuid> schemas.",
    no_args_is_help=True,
)


@app.command("install")
def install(
    path: str = typer.Argument(..., help="Local path to a candidate module directory."),
) -> None:
    """Gate + install a module from a local path."""
    asyncio.run(_install(Path(path)))


async def _install(source: Path) -> None:
    from parcel_shell.sandbox import service as sandbox_service

    if not source.exists() or not source.is_dir():
        typer.echo(f"error: {source} is not a directory", err=True)
        raise typer.Exit(2)
    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        settings = fast_app.state.settings
        async with sessionmaker() as db:
            try:
                row = await sandbox_service.create_sandbox(
                    db,
                    source_dir=source,
                    app=fast_app,
                    settings=settings,
                )
            except sandbox_service.GateRejected as exc:
                typer.echo("✗ gate rejected:", err=True)
                for f in exc.report.errors:
                    typer.echo(
                        f"  [{f.check}] {f.path}:{f.line} {f.rule}: {f.message}",
                        err=True,
                    )
                raise typer.Exit(1) from None
            await db.commit()
    typer.echo(f"✓ sandbox {row.id} at {row.url_prefix}")


@app.command("list")
def list_cmd() -> None:
    """List sandboxes."""
    asyncio.run(_list())


async def _list() -> None:
    from sqlalchemy import select

    from parcel_shell.sandbox.models import SandboxInstall

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        async with sessionmaker() as db:
            rows = (
                (
                    await db.execute(
                        select(SandboxInstall).order_by(SandboxInstall.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
    if not rows:
        typer.echo("no sandboxes")
        return
    typer.echo(f"{'ID':<36}  {'NAME':<16}  {'VER':<8}  STATUS     GATE   CREATED")
    for r in rows:
        gate = "pass" if r.gate_report.get("passed") else "FAIL"
        typer.echo(
            f"{str(r.id):<36}  {r.name:<16}  {r.version:<8}  "
            f"{r.status:<9}  {gate:<4}  {r.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


@app.command("show")
def show(sandbox_id: str = typer.Argument(...)) -> None:
    """Print a sandbox's full gate report."""
    asyncio.run(_show(UUID(sandbox_id)))


async def _show(sandbox_id: UUID) -> None:
    from parcel_shell.sandbox.models import SandboxInstall

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        async with sessionmaker() as db:
            row = await db.get(SandboxInstall, sandbox_id)
            if row is None:
                typer.echo(f"sandbox {sandbox_id} not found", err=True)
                raise typer.Exit(1)
    typer.echo(f"name:    {row.name} v{row.version}")
    typer.echo(f"status:  {row.status}")
    typer.echo(f"url:     {row.url_prefix}")
    typer.echo(f"schema:  {row.schema_name}")
    typer.echo(f"caps:    {', '.join(row.declared_capabilities) or '—'}")
    rep = row.gate_report
    passed = "✓ pass" if rep.get("passed") else "✗ FAIL"
    errors = [f for f in rep["findings"] if f["severity"] == "error"]
    warnings = [f for f in rep["findings"] if f["severity"] == "warning"]
    typer.echo(f"gate:    {passed}  ({len(errors)} errors, {len(warnings)} warnings)")
    for f in errors + warnings:
        typer.echo(
            f"  [{f['severity']:7}] {f['check']:10} {f['path']}:{f['line']} "
            f"{f['rule']}: {f['message']}"
        )


@app.command("promote")
def promote(
    sandbox_id: str = typer.Argument(...),
    name: str = typer.Argument(..., help="Target module name."),
    capability: list[str] = typer.Option(  # noqa: B008
        [], "--capability", "-c", help="Approve a declared capability. Repeatable."
    ),
) -> None:
    """Promote a sandbox to a real module install."""
    asyncio.run(_promote(UUID(sandbox_id), name, capability))


async def _promote(sandbox_id: UUID, name: str, capabilities: list[str]) -> None:
    from parcel_shell.sandbox import service as sandbox_service

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        settings = fast_app.state.settings
        async with sessionmaker() as db:
            try:
                installed = await sandbox_service.promote_sandbox(
                    db,
                    sandbox_id,
                    target_name=name,
                    approve_capabilities=capabilities,
                    app=fast_app,
                    settings=settings,
                )
            except sandbox_service.SandboxNotFound:
                typer.echo(f"sandbox {sandbox_id} not found", err=True)
                raise typer.Exit(1) from None
            except sandbox_service.TargetNameTaken as exc:
                typer.echo(f"target name already taken: {exc}", err=True)
                raise typer.Exit(1) from None
            await db.commit()
    typer.echo(f"✓ promoted to {installed.name}@{installed.version}")


@app.command("dismiss")
def dismiss(sandbox_id: str = typer.Argument(...)) -> None:
    """Drop the sandbox schema and remove files."""
    asyncio.run(_dismiss(UUID(sandbox_id)))


async def _dismiss(sandbox_id: UUID) -> None:
    from parcel_shell.sandbox import service as sandbox_service

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        async with sessionmaker() as db:
            try:
                await sandbox_service.dismiss_sandbox(db, sandbox_id, fast_app)
            except sandbox_service.SandboxNotFound:
                typer.echo(f"sandbox {sandbox_id} not found", err=True)
                raise typer.Exit(1) from None
            await db.commit()
    typer.echo(f"dismissed {sandbox_id}")


@app.command("prune")
def prune() -> None:
    """Dismiss expired sandboxes."""
    asyncio.run(_prune())


async def _prune() -> None:
    from parcel_shell.sandbox import service as sandbox_service

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        async with sessionmaker() as db:
            count = await sandbox_service.prune_expired(db, fast_app, now=datetime.now(UTC))
            await db.commit()
    typer.echo(f"dismissed {count} expired sandbox(es)")


@app.command("previews")
def previews(uuid_str: str = typer.Argument(..., metavar="UUID")) -> None:
    """Show preview render status for a sandbox."""
    asyncio.run(_previews(UUID(uuid_str)))


async def _previews(sandbox_id: UUID) -> None:
    from parcel_shell.sandbox.models import SandboxInstall

    async with with_shell() as fast_app:
        sessionmaker = fast_app.state.sessionmaker
        async with sessionmaker() as db:
            row = await db.get(SandboxInstall, sandbox_id)
            if row is None:
                typer.echo(f"sandbox {sandbox_id} not found", err=True)
                raise typer.Exit(2)
    ok = sum(1 for e in row.previews if e.get("status") == "ok")
    err = sum(1 for e in row.previews if e.get("status") == "error")
    typer.echo(f"sandbox {row.id}: preview_status={row.preview_status} (ok={ok}, error={err})")
    typer.echo(f"images dir: {row.module_root}/previews")
