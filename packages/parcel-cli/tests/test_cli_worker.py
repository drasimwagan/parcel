from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_worker_command_help_renders() -> None:
    r = runner.invoke(app, ["worker", "--help"])
    assert r.exit_code == 0
    assert "worker" in r.output.lower()


def test_worker_command_invokes_arq_run_worker(monkeypatch) -> None:
    """Invoking `parcel worker` calls arq.run_worker with WorkerSettings."""
    captured: dict = {}

    def fake_run_worker(settings_cls, **kwargs):
        captured["settings_cls"] = settings_cls
        return None

    def fake_build(_settings):
        class FakeSettings:
            functions: list = []
            cron_jobs: list = []

        return FakeSettings

    monkeypatch.setattr("arq.run_worker", fake_run_worker)
    monkeypatch.setattr(
        "parcel_shell.workflows.worker.build_worker_settings",
        fake_build,
    )
    r = runner.invoke(app, ["worker"])
    assert r.exit_code == 0, r.output
    assert captured.get("settings_cls") is not None
    assert hasattr(captured["settings_cls"], "functions")
