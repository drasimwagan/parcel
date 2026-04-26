from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_sandbox_help_lists_subcommands() -> None:
    result = runner.invoke(app, ["sandbox", "--help"])
    assert result.exit_code == 0
    for name in ("install", "list", "show", "promote", "dismiss", "prune", "previews"):
        assert name in result.stdout


def test_sandbox_promote_help_shows_capability_flag() -> None:
    result = runner.invoke(app, ["sandbox", "promote", "--help"])
    assert result.exit_code == 0
    assert "--capability" in result.stdout


def test_previews_subcommand_prints_status(monkeypatch, capsys) -> None:
    """`parcel sandbox previews <uuid>` reports preview_status + counts."""
    import uuid
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from parcel_cli.commands import sandbox as sandbox_cmd

    sb_id = uuid.uuid4()
    fake_row = MagicMock()
    fake_row.id = sb_id
    fake_row.preview_status = "ready"
    fake_row.previews = [
        {"route": "/a", "viewport": 375, "filename": "x.png", "status": "ok"},
        {"route": "/b", "viewport": 768, "filename": None, "status": "error"},
    ]
    fake_row.module_root = "/tmp/sandbox-x"

    fake_session = AsyncMock()
    fake_session.get = AsyncMock(return_value=fake_row)

    fake_factory = MagicMock()
    fake_factory.return_value.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    fake_app = SimpleNamespace(
        state=SimpleNamespace(sessionmaker=fake_factory)
    )

    @asynccontextmanager
    async def _with_shell():
        yield fake_app

    monkeypatch.setattr(sandbox_cmd, "with_shell", _with_shell)

    sandbox_cmd.previews(str(sb_id))
    captured = capsys.readouterr()
    assert "ready" in captured.out
    assert "ok=1" in captured.out
    assert "error=1" in captured.out
