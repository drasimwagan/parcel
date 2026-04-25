from __future__ import annotations

import os

import typer
import uvicorn


def dev(
    host: str = typer.Option("0.0.0.0", "--host"),  # noqa: S104
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Run the shell with hot-reload (development).

    Sets PARCEL_WORKFLOWS_INLINE=1 so workflows fire in-process without
    needing the worker. Cron triggers won't fire under inline mode — start
    `parcel worker` separately if you need scheduled workflows.
    """
    os.environ.setdefault("PARCEL_ENV", "dev")
    os.environ["PARCEL_WORKFLOWS_INLINE"] = "1"
    typer.echo(
        "workflows running inline (sync triggers); cron triggers off — "
        "start `parcel worker` for scheduled workflows."
    )
    uvicorn.run(
        "parcel_shell.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
