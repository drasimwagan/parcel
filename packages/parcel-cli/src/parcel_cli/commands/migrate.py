from __future__ import annotations

import typer


def migrate(
    module: str | None = typer.Option(None, "--module", help="Only migrate one module."),
) -> None:
    """Run migrations for the shell and active modules."""
    raise typer.Exit(0)
