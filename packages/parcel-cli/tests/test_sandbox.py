from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_sandbox_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["sandbox", "--help"])
    assert result.exit_code == 0
    for name in ("install", "list", "show", "promote", "dismiss", "prune"):
        assert name in result.stdout


def test_sandbox_promote_help_shows_capability_flag() -> None:
    result = runner.invoke(app, ["sandbox", "promote", "--help"])
    assert result.exit_code == 0
    assert "--capability" in result.stdout
