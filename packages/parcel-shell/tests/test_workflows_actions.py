"""Phase 10c rich-action executor tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from parcel_sdk import (
    CallWebhook,
    GenerateReport,
    RunModuleFunction,
    SendEmail,
    WorkflowContext,
)

pytestmark = pytest.mark.asyncio


def _ctx(session=None) -> WorkflowContext:
    return WorkflowContext(
        session=session,  # type: ignore[arg-type]
        event="t.e",
        subject=None,
        subject_id=None,
        changed=(),
    )


# ---- SendEmail -------------------------------------------------------------


async def test_send_email_raises_when_smtp_not_configured(monkeypatch) -> None:
    from parcel_shell.config import Settings, get_settings
    from parcel_shell.workflows.actions.email import execute_send_email

    fake = Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": "postgresql+asyncpg://x/y",
            "REDIS_URL": "redis://localhost:1",
            "PARCEL_SMTP_HOST": None,  # explicit None
        }
    )
    get_settings.cache_clear()
    monkeypatch.setattr(
        "parcel_shell.workflows.actions.email.get_settings", lambda: fake
    )

    payload: dict[str, Any] = {}
    with pytest.raises(RuntimeError, match="SMTP not configured"):
        await execute_send_email(
            SendEmail(to="x@y.com", subject="s", body="b"), _ctx(), payload
        )


async def test_send_email_calls_smtp_when_configured(monkeypatch) -> None:
    from parcel_shell.config import Settings, get_settings
    from parcel_shell.workflows.actions.email import execute_send_email

    fake = Settings.model_validate(
        {
            "PARCEL_ENV": "dev",
            "PARCEL_SESSION_SECRET": "x" * 32,
            "DATABASE_URL": "postgresql+asyncpg://x/y",
            "REDIS_URL": "redis://localhost:1",
            "PARCEL_SMTP_HOST": "smtp.example.com",
            "PARCEL_SMTP_FROM_ADDRESS": "from@example.com",
        }
    )
    get_settings.cache_clear()
    monkeypatch.setattr(
        "parcel_shell.workflows.actions.email.get_settings", lambda: fake
    )

    sent: list[Any] = []

    class FakeSMTP:
        def __init__(self, host, port):
            sent.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, msg):
            sent.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr("parcel_shell.workflows.actions.email.smtplib.SMTP", FakeSMTP)

    payload: dict[str, Any] = {}
    await execute_send_email(
        SendEmail(to="ada@example.com", subject="hello", body="world"),
        _ctx(),
        payload,
    )
    assert payload["emails_sent"] == ["ada@example.com"]
    assert ("init", "smtp.example.com", 587) in sent


# ---- CallWebhook -----------------------------------------------------------


async def test_call_webhook_posts_and_captures_response(monkeypatch) -> None:
    import httpx

    from parcel_shell.workflows.actions.webhook import execute_call_webhook

    captured: dict = {}

    def fake_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["json"] = request.read().decode()
        return httpx.Response(200, json={"ok": True}, text='{"ok": true}')

    transport = httpx.MockTransport(fake_handler)

    real_client = httpx.AsyncClient

    class _PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        "parcel_shell.workflows.actions.webhook.httpx.AsyncClient", _PatchedClient
    )

    payload: dict[str, Any] = {}
    await execute_call_webhook(
        CallWebhook(url="https://example.com/hook", body={"x": 1}),
        _ctx(),
        payload,
    )
    assert captured["url"] == "https://example.com/hook"
    assert captured["method"] == "POST"
    assert payload["webhook_calls"][0]["status"] == 200


async def test_call_webhook_raises_on_non_2xx(monkeypatch) -> None:
    import httpx

    from parcel_shell.workflows.actions.webhook import execute_call_webhook

    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="boom")
    )
    real_client = httpx.AsyncClient

    class _PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        "parcel_shell.workflows.actions.webhook.httpx.AsyncClient", _PatchedClient
    )

    with pytest.raises(httpx.HTTPStatusError):
        await execute_call_webhook(
            CallWebhook(url="https://example.com/hook"),
            _ctx(),
            {},
        )


# ---- RunModuleFunction -----------------------------------------------------


async def test_run_module_function_invokes_registered(monkeypatch) -> None:
    from parcel_sdk import Module

    from parcel_shell.workflows.actions.module_function import (
        execute_run_module_function,
    )

    async def _audit(_ctx) -> str:
        return "ran"

    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(
                    name="demo", version="0.1.0", workflow_functions={"audit": _audit}
                )
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload: dict[str, Any] = {}
    await execute_run_module_function(
        RunModuleFunction(module="demo", function="audit"), _ctx(), payload
    )
    assert payload["function_calls"][0]["return"] == "ran"


async def test_run_module_function_raises_on_unknown_module(monkeypatch) -> None:
    from parcel_shell.workflows.actions.module_function import (
        execute_run_module_function,
    )

    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest={}))
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    with pytest.raises(RuntimeError, match="not active"):
        await execute_run_module_function(
            RunModuleFunction(module="nope", function="audit"), _ctx(), {}
        )


async def test_run_module_function_raises_on_unknown_function(monkeypatch) -> None:
    from parcel_sdk import Module

    from parcel_shell.workflows.actions.module_function import (
        execute_run_module_function,
    )

    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflow_functions={})
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    with pytest.raises(RuntimeError, match="not registered"):
        await execute_run_module_function(
            RunModuleFunction(module="demo", function="missing"), _ctx(), {}
        )


# ---- GenerateReport -------------------------------------------------------


async def test_generate_report_raises_on_missing_report(monkeypatch) -> None:
    from parcel_shell.workflows.actions.report import execute_generate_report

    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest={}))
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    with pytest.raises(RuntimeError, match="not found"):
        await execute_generate_report(
            GenerateReport(module="nope", slug="none"), _ctx(), {}
        )
