from __future__ import annotations

import json
import logging

import structlog

from parcel_shell.logging import configure_logging, request_id_var


def test_configure_logging_dev_uses_console_renderer(capsys) -> None:
    configure_logging(env="dev", level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", key="value")
    out = capsys.readouterr().out
    assert "hello" in out
    assert "key" in out and "value" in out


def test_configure_logging_prod_emits_json(capsys) -> None:
    configure_logging(env="prod", level="INFO")
    log = structlog.get_logger("test")
    log.info("hello", key="value")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["key"] == "value"
    assert payload["level"] == "info"


def test_request_id_contextvar_bound_in_logs(capsys) -> None:
    configure_logging(env="prod", level="INFO")
    token = request_id_var.set("req-abc")
    try:
        structlog.get_logger("test").info("with-id")
    finally:
        request_id_var.reset(token)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["request_id"] == "req-abc"


def test_configure_logging_is_idempotent() -> None:
    configure_logging(env="dev", level="INFO")
    configure_logging(env="dev", level="DEBUG")
    assert logging.getLogger().level == logging.DEBUG
