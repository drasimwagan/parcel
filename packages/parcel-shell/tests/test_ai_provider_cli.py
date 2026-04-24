from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from parcel_shell.ai.provider import ClaudeCodeCLIProvider, ProviderError


def _write_tree(root: Path, tree: dict[str, str]) -> None:
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


@pytest.mark.asyncio
async def test_cli_provider_happy_path(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'parcel-mod-x'\n",
            "src/parcel_mod_x/__init__.py": "# x",
        },
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"result": "done", "tokens": 100}),
            stderr="",
        )

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        gen = await p.generate("track invoices", tmp_path)
    assert "pyproject.toml" in gen.files
    assert "src/parcel_mod_x/__init__.py" in gen.files


@pytest.mark.asyncio
async def test_cli_provider_nonzero_exit_is_provider_error(tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="boom")

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        with pytest.raises(ProviderError, match="exit 2"):
            await p.generate("x", tmp_path)


@pytest.mark.asyncio
async def test_cli_provider_empty_tree_is_provider_error(tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        with pytest.raises(ProviderError, match="no files"):
            await p.generate("x", tmp_path)


@pytest.mark.asyncio
async def test_cli_provider_skips_gate_report_and_pycache(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "pyproject.toml": "[project]\nname = 'parcel-mod-x'\n",
            "GATE_REPORT.md": "previous failures",
            "__pycache__/foo.pyc": "",
        },
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        gen = await p.generate("x", tmp_path)
    assert list(gen.files) == ["pyproject.toml"]
