from __future__ import annotations

import typer
import uvicorn


def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    workers: int = typer.Option(1, "--workers"),
) -> None:
    """Run the shell in production mode."""
    uvicorn.run(
        "parcel_shell.app:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers,
        log_level="info",
    )
