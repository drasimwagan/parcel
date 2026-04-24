from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_install_help_describes_source() -> None:
    result = runner.invoke(app, ["install", "--help"])
    assert result.exit_code == 0
    assert "source" in result.stdout.lower() or "SOURCE" in result.stdout
    assert "--skip-pip" in result.stdout
