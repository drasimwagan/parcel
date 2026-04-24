from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_ai_help_lists_generate() -> None:
    result = runner.invoke(app, ["ai", "--help"])
    assert result.exit_code == 0
    assert "generate" in result.stdout


def test_ai_generate_help_lists_prompt_arg() -> None:
    result = runner.invoke(app, ["ai", "generate", "--help"])
    assert result.exit_code == 0
    combined = result.stdout.lower()
    assert "prompt" in combined
