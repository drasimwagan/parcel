from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_migrate_help_lists_module_flag() -> None:
    result = runner.invoke(app, ["migrate", "--help"])
    assert result.exit_code == 0
    assert "--module" in result.stdout
