from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_dev_invokes_uvicorn_with_reload() -> None:
    with patch("parcel_cli.commands.dev.uvicorn.run") as m:
        result = runner.invoke(app, ["dev", "--port", "9999"])
        assert result.exit_code == 0, result.stdout
        args, kwargs = m.call_args
        assert args[0] == "parcel_shell.app:create_app"
        assert kwargs["factory"] is True
        assert kwargs["reload"] is True
        assert kwargs["port"] == 9999


def test_dev_no_reload_flag() -> None:
    with patch("parcel_cli.commands.dev.uvicorn.run") as m:
        result = runner.invoke(app, ["dev", "--no-reload"])
        assert result.exit_code == 0
        assert m.call_args.kwargs["reload"] is False


def test_serve_invokes_uvicorn_with_workers() -> None:
    with patch("parcel_cli.commands.serve.uvicorn.run") as m:
        result = runner.invoke(app, ["serve", "--workers", "3"])
        assert result.exit_code == 0, result.stdout
        kwargs = m.call_args.kwargs
        assert kwargs["workers"] == 3
        assert kwargs["factory"] is True
        assert "reload" not in kwargs
