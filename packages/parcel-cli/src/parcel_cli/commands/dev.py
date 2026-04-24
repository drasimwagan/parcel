from __future__ import annotations

import typer


def dev(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Run the shell with hot-reload (development)."""
    raise typer.Exit(0)
