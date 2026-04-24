"""Parcel CLI entry point."""

from __future__ import annotations

import typer

from parcel_cli.commands import dev, install, migrate, new_module, sandbox, serve

app = typer.Typer(
    name="parcel",
    help="Parcel — AI-native modular business-app platform CLI.",
    no_args_is_help=True,
)

app.command(name="new-module")(new_module.new_module)
app.command(name="install")(install.install)
app.command(name="migrate")(migrate.migrate)
app.command(name="dev")(dev.dev)
app.command(name="serve")(serve.serve)
app.add_typer(sandbox.app, name="sandbox")


if __name__ == "__main__":  # pragma: no cover
    app()
