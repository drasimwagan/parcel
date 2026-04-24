from __future__ import annotations

import asyncio

import typer

from parcel_cli._shell import with_shell


def migrate(
    module: str | None = typer.Option(None, "--module", help="Only migrate one module."),
) -> None:
    """Upgrade installed modules to head revision."""
    asyncio.run(_run(module))


async def _run(module: str | None) -> None:
    from parcel_shell.modules import service as module_service
    from parcel_shell.modules.discovery import discover_modules

    async with with_shell() as app:
        settings = app.state.settings
        sessionmaker = app.state.sessionmaker
        discovered = {d.module.name: d for d in discover_modules()}

        targets = [module] if module else list(discovered.keys())
        if not targets:
            typer.echo("no modules discovered")
            return

        async with sessionmaker() as db:
            for name in targets:
                if name not in discovered:
                    typer.echo(f"  ! {name}: not discovered, skipping")
                    continue
                try:
                    row = await module_service.upgrade_module(
                        db,
                        name=name,
                        discovered=discovered,
                        database_url=settings.database_url,
                    )
                    typer.echo(f"  ✓ {name}: at {row.last_migrated_rev}")
                except module_service.ModuleNotDiscovered:
                    typer.echo(f"  ! {name}: not installed, skipping")
                except module_service.ModuleMigrationFailed as exc:
                    typer.echo(f"  ✗ {name}: migration failed: {exc}")
                    raise typer.Exit(1) from exc
            await db.commit()
