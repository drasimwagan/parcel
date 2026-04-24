from __future__ import annotations

import os

import typer
import uvicorn


def dev(
    host: str = typer.Option("0.0.0.0", "--host"),  # noqa: S104
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Run the shell with hot-reload (development)."""
    os.environ.setdefault("PARCEL_ENV", "dev")
    uvicorn.run(
        "parcel_shell.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
