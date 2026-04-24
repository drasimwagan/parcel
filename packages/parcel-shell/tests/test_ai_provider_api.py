from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from parcel_shell.ai.provider import AnthropicAPIProvider, ProviderError


def _tool_use(name: str, payload: dict, uid: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=payload, id=uid)


def _msg(content: list, stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop_reason, id="m1")


def _fake_client(responses: list) -> AsyncMock:
    client = AsyncMock()
    client.messages.create = AsyncMock(side_effect=responses)
    return client


@pytest.mark.asyncio
async def test_api_provider_happy_path(tmp_path: Path) -> None:
    responses = [
        _msg(
            [
                _tool_use("write_file", {"path": "pyproject.toml", "content": "x"}, "t1"),
                _tool_use(
                    "write_file",
                    {"path": "src/x/__init__.py", "content": "# ok"},
                    "t2",
                ),
                _tool_use("submit_module", {}, "t3"),
            ],
            "tool_use",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    gen = await p.generate("track invoices", tmp_path)
    assert "pyproject.toml" in gen.files
    assert gen.files["pyproject.toml"] == b"x"
    assert gen.files["src/x/__init__.py"] == b"# ok"


@pytest.mark.asyncio
async def test_api_provider_rejects_absolute_path(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "/etc/passwd", "content": "x"}, "t1")],
            "tool_use",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    with pytest.raises(ProviderError, match="absolute"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_rejects_parent_traversal(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "../leak.py", "content": "x"}, "t1")],
            "tool_use",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    with pytest.raises(ProviderError, match="traversal"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_rejects_oversize_content(tmp_path: Path) -> None:
    huge = "a" * (70 * 1024)
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "huge.py", "content": huge}, "t1")],
            "tool_use",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    with pytest.raises(ProviderError, match="too large"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_missing_submit_is_error(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "a.py", "content": "# x"}, "t1")],
            "end_turn",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    with pytest.raises(ProviderError, match="submit_module"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_rejects_disallowed_extension(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "x.sh", "content": "echo hi"}, "t1")],
            "tool_use",
        )
    ]
    p = AnthropicAPIProvider(api_key="sk-test", client=_fake_client(responses))
    with pytest.raises(ProviderError, match="disallowed extension"):
        await p.generate("bad", tmp_path)
