from __future__ import annotations

import typer


def install(
    source: str = typer.Argument(..., help="Local path or Git URL of a Parcel module."),
) -> None:
    """Install a Parcel module and register it with the shell."""
    raise typer.Exit(0)
