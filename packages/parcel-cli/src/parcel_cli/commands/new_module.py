from __future__ import annotations

import typer


def new_module(
    name: str = typer.Argument(..., help="Module name (snake_case)."),
    path: str = typer.Option("./modules", "--path", help="Destination directory."),
    force: bool = typer.Option(False, "--force", help="Overwrite if target exists."),
) -> None:
    """Scaffold a new Parcel module."""
    raise typer.Exit(0)
