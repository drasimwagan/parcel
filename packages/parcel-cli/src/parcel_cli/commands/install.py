from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import typer

from parcel_cli._shell import with_shell


def install(
    source: str = typer.Argument(..., help="Local path or Git URL of a Parcel module."),
    skip_pip: bool = typer.Option(
        False, "--skip-pip", help="Skip pip install (module already importable)."
    ),
) -> None:
    """Install a Parcel module and register it with the shell."""
    if not skip_pip:
        _pip_install(source)
    asyncio.run(_activate())


def _pip_install(source: str) -> None:
    p = Path(source)
    cmd = ["uv", "pip", "install", "-e", str(p)] if p.exists() else ["uv", "pip", "install", source]
    typer.echo(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
    if result.returncode != 0:
        if result.stdout:
            typer.echo(result.stdout)
        if result.stderr:
            typer.echo(result.stderr, err=True)
        raise typer.Exit(result.returncode)


async def _activate() -> None:
    from parcel_shell.modules import service as module_service
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    async with with_shell() as app:
        settings = app.state.settings
        sessionmaker = app.state.sessionmaker
        discovered = {d.module.name: d for d in discover_modules()}

        if not discovered:
            typer.echo("error: no Parcel modules discovered", err=True)
            raise typer.Exit(1)

        async with sessionmaker() as db:
            installed_any = False
            for name, d in discovered.items():
                existing = await db.get(InstalledModule, name)
                if existing is not None:
                    typer.echo(f"  · {name}: already installed (v{existing.version})")
                    continue
                try:
                    row = await module_service.install_module(
                        db,
                        name=name,
                        approve_capabilities=list(d.module.capabilities),
                        discovered=discovered,
                        database_url=settings.database_url,
                        app=app,
                    )
                    typer.echo(f"  ✓ installed {row.name}@{row.version}")
                    if d.module.capabilities:
                        typer.echo(
                            "    auto-approved capabilities: " + ", ".join(d.module.capabilities)
                        )
                    if d.module.permissions:
                        typer.echo(
                            "    permissions: " + ", ".join(p.name for p in d.module.permissions)
                        )
                    installed_any = True
                except module_service.ModuleAlreadyInstalled:
                    typer.echo(f"  · {name}: already installed")
            if not installed_any:
                typer.echo("nothing to activate")
            await db.commit()
