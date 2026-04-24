# Phase 7b — Claude Generator — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Ship the Claude API generator — given a natural-language prompt, produce a candidate module and hand it to the Phase 7a sandbox pipeline. No chat UI, no streaming, no ARQ. One HTTP endpoint + one CLI subcommand + two provider implementations behind a common interface.

**Architecture:** `ClaudeProvider` protocol with `AnthropicAPIProvider` (default, SDK + our `write_file`/`submit_module` tools) and `ClaudeCodeCLIProvider` (subprocess, `--output-format json`). Both emit `GeneratedFiles` into a throwaway temp dir. `generate_module()` zips them, calls `create_sandbox()` (Phase 7a), and retries once on gate rejection with the gate report attached.

**Tech stack:** Python 3.12, FastAPI, SQLAlchemy, `anthropic>=0.40`, typer, `subprocess` for CLI provider.

**Spec:** [docs/superpowers/specs/2026-04-23-phase-7b-claude-generator-design.md](../specs/2026-04-23-phase-7b-claude-generator-design.md)

---

## Part A — Provider infrastructure

### Task A1: `ai/` package skeleton + `ClaudeProvider` protocol + dataclasses

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/__init__.py`
- Create: `packages/parcel-shell/src/parcel_shell/ai/provider.py`
- Modify: `packages/parcel-shell/pyproject.toml` (add `anthropic>=0.40`)

- [ ] **Step 1: Write the `ai/__init__.py`** — one-line docstring.

- [ ] **Step 2: Write the `provider.py`** with the dataclasses and Protocol:

```python
# parcel_shell/ai/provider.py
"""Claude provider abstraction — API or CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class GeneratedFiles:
    files: dict[str, bytes]       # POSIX-relative path → content
    transcript: str


@dataclass(frozen=True)
class PriorAttempt:
    gate_report_json: str
    previous_files: dict[str, bytes]


class ProviderError(Exception):
    """Network failure, auth failure, malformed output, tool-use contract violated."""


class ClaudeProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        working_dir: Path,
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles: ...
```

- [ ] **Step 3: Add `anthropic>=0.40` to `parcel-shell` runtime deps.**

In `packages/parcel-shell/pyproject.toml`'s `[project].dependencies`, add `"anthropic>=0.40,<1.0"`.

- [ ] **Step 4: `uv sync --all-packages`** and verify `python -c "from parcel_shell.ai.provider import ClaudeProvider, ProviderError; print('ok')"`.

- [ ] **Step 5: Commit** — `feat(ai): provider protocol and dataclasses for Claude generator`

---

### Task A2: `AnthropicAPIProvider`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ai/provider.py`
- Create: `packages/parcel-shell/src/parcel_shell/ai/prompts/__init__.py` (empty, for resource loading)
- Create: `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` (placeholder — populated in Task A4)
- Create: `packages/parcel-shell/tests/test_ai_provider_api.py`

- [ ] **Step 1: Write a placeholder prompt file.** One line of content — Task A4 fills it in properly. Existence matters now so `importlib.resources` works.

```
# generate_module.md (placeholder)
You are writing a Parcel module. Tool contract TBD — see Task A4.
```

- [ ] **Step 2: Write failing tests.** The tests use a fake Anthropic client that records `messages.create` calls and returns scripted `tool_use` sequences.

```python
# packages/parcel-shell/tests/test_ai_provider_api.py
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from parcel_shell.ai.provider import (
    AnthropicAPIProvider,
    ProviderError,
)


def _tool_use(tool_name: str, tool_input: dict, tool_use_id: str):
    return SimpleNamespace(
        type="tool_use",
        name=tool_name,
        input=tool_input,
        id=tool_use_id,
    )


def _text(text: str):
    return SimpleNamespace(type="text", text=text)


def _msg(content: list, stop_reason: str):
    return SimpleNamespace(content=content, stop_reason=stop_reason, id="m1")


@pytest.mark.asyncio
async def test_api_provider_happy_path(tmp_path: Path) -> None:
    responses = [
        _msg(
            [
                _tool_use("write_file", {"path": "pyproject.toml", "content": "..."}, "t1"),
                _tool_use("write_file", {"path": "src/x/__init__.py", "content": "# ok"}, "t2"),
                _tool_use("submit_module", {}, "t3"),
            ],
            "tool_use",
        )
    ]
    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(side_effect=responses)

    p = AnthropicAPIProvider(
        api_key="sk-test", model="claude-opus-4-7", client=fake_client
    )
    gen = await p.generate("track invoices", tmp_path)
    assert "pyproject.toml" in gen.files
    assert "src/x/__init__.py" in gen.files
    assert gen.files["pyproject.toml"] == b"..."


@pytest.mark.asyncio
async def test_api_provider_rejects_absolute_path(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "/etc/passwd", "content": "x"}, "t1")],
            "tool_use",
        )
    ]
    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(side_effect=responses)

    p = AnthropicAPIProvider(api_key="sk-test", client=fake_client)
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
    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(side_effect=responses)

    p = AnthropicAPIProvider(api_key="sk-test", client=fake_client)
    with pytest.raises(ProviderError, match="traversal"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_rejects_oversize_content(tmp_path: Path) -> None:
    big = "a" * (70 * 1024)  # 70 KiB, over the 64 KiB per-file cap
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "huge.py", "content": big}, "t1")],
            "tool_use",
        )
    ]
    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(side_effect=responses)

    p = AnthropicAPIProvider(api_key="sk-test", client=fake_client)
    with pytest.raises(ProviderError, match="too large"):
        await p.generate("bad", tmp_path)


@pytest.mark.asyncio
async def test_api_provider_missing_submit_is_error(tmp_path: Path) -> None:
    responses = [
        _msg(
            [_tool_use("write_file", {"path": "a.py", "content": "# x"}, "t1")],
            "end_turn",  # stops without submit_module
        )
    ]
    fake_client = AsyncMock()
    fake_client.messages.create = AsyncMock(side_effect=responses)

    p = AnthropicAPIProvider(api_key="sk-test", client=fake_client)
    with pytest.raises(ProviderError, match="submit_module"):
        await p.generate("bad", tmp_path)
```

- [ ] **Step 3: Implement `AnthropicAPIProvider`.** Append to `provider.py`:

```python
# provider.py (continued)
import asyncio
import hashlib
from importlib import resources
from typing import Any

MAX_FILE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 1 * 1024 * 1024


def _load_system_prompt() -> str:
    from parcel_shell.ai import prompts
    return resources.files(prompts).joinpath("generate_module.md").read_text(encoding="utf-8")


_TOOLS = [
    {
        "name": "write_file",
        "description": "Write a file into the module root. Paths must be relative POSIX paths without '..' segments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "submit_module",
        "description": "Call exactly once when the module is complete.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


class AnthropicAPIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-opus-4-7",
        max_tokens: int = 8192,
        timeout_s: float = 120.0,
        client: Any = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._timeout_s = timeout_s
        if client is None:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._client = client

    async def generate(
        self,
        prompt: str,
        working_dir: Path,
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles:
        system = _load_system_prompt()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        if prior is not None:
            messages.append({
                "role": "assistant",
                "content": f"(previous attempt — {len(prior.previous_files)} files)",
            })
            messages.append({
                "role": "user",
                "content": (
                    "The previous attempt failed the static gate. "
                    "Here is the gate report JSON. Fix the issues it reports "
                    "and emit a corrected full module via write_file + submit_module.\n\n"
                    + prior.gate_report_json
                ),
            })

        files: dict[str, bytes] = {}
        total_bytes = 0
        transcript_parts: list[str] = []
        submitted = False

        # Anthropic tool-use loop. We loop up to 20 times as a hard safety cap —
        # well above the ~5-15 tool calls a reasonable module requires.
        for _ in range(20):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=_TOOLS,
                messages=messages,
            )
            transcript_parts.append(f"stop_reason={response.stop_reason}")
            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            # Record assistant content for next turn
            messages.append({
                "role": "assistant",
                "content": response.content if isinstance(response.content, list) else [response.content],
            })

            tool_results = []
            for tu in tool_uses:
                if tu.name == "submit_module":
                    submitted = True
                    tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "ok"})
                    continue
                if tu.name != "write_file":
                    raise ProviderError(f"unknown tool call: {tu.name}")
                path = tu.input.get("path", "")
                content = tu.input.get("content", "")
                _validate_path(path)
                data = content.encode("utf-8")
                if len(data) > MAX_FILE_BYTES:
                    raise ProviderError(f"write_file content too large: {len(data)} bytes")
                total_bytes += len(data)
                if total_bytes > MAX_TOTAL_BYTES:
                    raise ProviderError(f"total generated bytes too large: {total_bytes}")
                files[path] = data
                tool_results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "ok"})

            if submitted:
                break

            if response.stop_reason != "tool_use":
                raise ProviderError(
                    f"model stopped (reason={response.stop_reason}) without calling submit_module"
                )

            # Feed tool_results back as the next user turn.
            messages.append({"role": "user", "content": tool_results})

        if not submitted:
            raise ProviderError("exceeded tool-use iteration cap without submit_module")

        if not files:
            raise ProviderError("submit_module called with no files written")

        return GeneratedFiles(files=files, transcript="\n".join(transcript_parts))


def _validate_path(path: str) -> None:
    if not path:
        raise ProviderError("write_file path is empty")
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        raise ProviderError(f"write_file path must not be absolute: {path!r}")
    if any(part == ".." for part in path.replace("\\", "/").split("/")):
        raise ProviderError(f"write_file path has '..' traversal: {path!r}")
    if any(path.lower().endswith(ext) for ext in (".sh", ".exe", ".so", ".dll", ".dylib")):
        raise ProviderError(f"write_file path has disallowed extension: {path!r}")
```

- [ ] **Step 4: Run tests.** Expected: 5 passed.

- [ ] **Step 5: Commit** — `feat(ai): AnthropicAPIProvider with write_file tool + path safety + 2-turn tool-use loop`

---

### Task A3: `ClaudeCodeCLIProvider`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ai/provider.py`
- Create: `packages/parcel-shell/tests/test_ai_provider_cli.py`

- [ ] **Step 1: Write failing tests.**

```python
# packages/parcel-shell/tests/test_ai_provider_cli.py
from __future__ import annotations

import json
from pathlib import Path
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
    # Pre-populate the working dir as the CLI would have.
    _write_tree(tmp_path, {
        "pyproject.toml": "[project]\nname = 'parcel-mod-x'\n",
        "src/parcel_mod_x/__init__.py": "# x",
    })

    def fake_run(*args, **kwargs):
        from types import SimpleNamespace
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
        from types import SimpleNamespace
        return SimpleNamespace(returncode=2, stdout="", stderr="boom")

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        with pytest.raises(ProviderError, match="exit 2"):
            await p.generate("x", tmp_path)


@pytest.mark.asyncio
async def test_cli_provider_empty_tree_is_provider_error(tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    with patch("parcel_shell.ai.provider.subprocess.run", fake_run):
        p = ClaudeCodeCLIProvider()
        with pytest.raises(ProviderError, match="no files"):
            await p.generate("x", tmp_path)
```

- [ ] **Step 2: Implement `ClaudeCodeCLIProvider`.** Append to `provider.py`:

```python
# provider.py (continued)
import asyncio
import subprocess


class ClaudeCodeCLIProvider:
    def __init__(
        self,
        *,
        claude_path: str = "claude",
        timeout_s: float = 180.0,
    ) -> None:
        self._claude_path = claude_path
        self._timeout_s = timeout_s

    async def generate(
        self,
        prompt: str,
        working_dir: Path,
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles:
        effective_prompt = prompt
        if prior is not None:
            (working_dir / "GATE_REPORT.md").write_text(
                "# Previous attempt failed the gate\n\n"
                + prior.gate_report_json,
                encoding="utf-8",
            )
            effective_prompt = (
                f"{prompt}\n\n"
                "Your previous attempt failed the static gate — see GATE_REPORT.md "
                "in the working directory for details. Fix the issues and produce a "
                "corrected module."
            )

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(  # noqa: S603, S607
                [
                    self._claude_path,
                    "-p",
                    effective_prompt,
                    "--output-format",
                    "json",
                    "--dangerously-skip-permissions",
                ],
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_s,
            )

        try:
            result = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"claude CLI timeout after {self._timeout_s}s") from exc
        except FileNotFoundError as exc:
            raise ProviderError(
                f"claude CLI not found at {self._claude_path!r}"
            ) from exc

        if result.returncode != 0:
            raise ProviderError(
                f"claude CLI exit {result.returncode}: {result.stderr.strip()[:500]}"
            )

        files: dict[str, bytes] = {}
        for p in sorted(working_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(working_dir)
            if rel.parts and rel.parts[0] in {".git", "__pycache__", "node_modules"}:
                continue
            if rel.name == "GATE_REPORT.md":
                continue
            files[rel.as_posix()] = p.read_bytes()

        if not files:
            raise ProviderError("claude CLI produced no files in the working directory")

        return GeneratedFiles(files=files, transcript=result.stdout)
```

- [ ] **Step 3: Run tests.** Expected: 3 passed.

- [ ] **Step 4: Commit** — `feat(ai): ClaudeCodeCLIProvider via subprocess with path-scoped working dir`

---

### Task A4: System prompt — `generate_module.md`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md`

- [ ] **Step 1: Draft the system prompt.** Sections:
  1. Role + goal (must pass a strict static gate, emit only tool calls, no prose).
  2. Tool contract (`write_file(path, content)` + `submit_module()`).
  3. Complete reference scaffold — copy the 7-file skeleton that `parcel new-module` emits (see `packages/parcel-cli/src/parcel_cli/scaffold/template_files.py`), annotated inline.
  4. Capability vocabulary — 4 values + default is none.
  5. Hard rules (what the gate always rejects).
  6. Allowed-import list.
  7. Style conventions.

Target 3-4k tokens. Commit as a plain markdown file.

- [ ] **Step 2: Verify the prompt loads.**

```
python -c "from parcel_shell.ai.provider import _load_system_prompt; print(len(_load_system_prompt()), 'chars')"
```

Expected: a reasonably-sized positive number.

- [ ] **Step 3: Commit** — `feat(ai): generator system prompt with scaffold, tool contract, capability vocab, hard rules`

---

## Part B — Orchestrator, config, app wiring

### Task B1: Settings additions

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/config.py`

- [ ] **Step 1: Extend `Settings`** with three new fields:

```python
    ai_provider: Literal["api", "cli"] = Field(default="api", alias="PARCEL_AI_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-opus-4-7", alias="PARCEL_ANTHROPIC_MODEL"
    )
```

No strict validator — an operator can boot the shell without a key and the generator endpoint will return 503 until configured.

- [ ] **Step 2: Commit** — `feat(config): settings for AI provider, key, and model`

---

### Task B2: `generate_module` orchestrator

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/generator.py`
- Create: `packages/parcel-shell/tests/_fake_provider.py`
- Create: `packages/parcel-shell/tests/test_ai_generator.py`

- [ ] **Step 1: Write `_fake_provider.py` fixture helper.**

```python
# packages/parcel-shell/tests/_fake_provider.py
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from parcel_shell.ai.provider import GeneratedFiles, PriorAttempt, ProviderError


@dataclass
class FakeProvider:
    """Hands out scripted GeneratedFiles in order.

    Each element in ``queue`` is either:
      - GeneratedFiles (returned as-is)
      - dict[str, bytes] (wrapped into GeneratedFiles)
      - an Exception (raised)
    """

    queue: list

    async def generate(self, prompt, working_dir, *, prior=None):
        if not self.queue:
            raise RuntimeError("FakeProvider exhausted")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, GeneratedFiles):
            return item
        return GeneratedFiles(files=item, transcript="fake")
```

- [ ] **Step 2: Write failing tests.**

```python
# packages/parcel-shell/tests/test_ai_generator.py
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI

from parcel_shell.ai.generator import GenerationFailure, generate_module
from parcel_shell.ai.provider import ProviderError
from parcel_shell.config import Settings
from parcel_shell.sandbox.models import SandboxInstall

from _fake_provider import FakeProvider

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _contacts_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for p in CONTACTS_SRC.rglob("*"):
        if "__pycache__" in p.parts or p.suffix in {".pyc"}:
            continue
        if p.is_file():
            files[str(p.relative_to(CONTACTS_SRC)).replace("\\", "/")] = p.read_bytes()
    return files


@pytest.mark.asyncio
async def test_generator_success_first_attempt(
    committing_app: FastAPI, settings: Settings
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

    fake = FakeProvider(queue=[_contacts_files()])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "track invoices",
                provider=fake, db=db, app=committing_app, settings=settings,
            )
            await db.commit()
        assert isinstance(result, SandboxInstall)
        assert result.name == "contacts"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generator_gate_fail_twice_returns_exceeded_retries(
    committing_app: FastAPI, settings: Settings, tmp_path: Path
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

    bad_files = {
        "pyproject.toml": b'[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n',
        "src/parcel_mod_bad/__init__.py": (
            b"import os\nfrom parcel_sdk import Module\n"
            b"module = Module(name='bad', version='0.1.0')\n"
        ),
    }
    fake = FakeProvider(queue=[bad_files, bad_files])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "bad prompt",
                provider=fake, db=db, app=committing_app, settings=settings,
            )
        assert isinstance(result, GenerationFailure)
        assert result.kind == "exceeded_retries"
        assert result.gate_report is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generator_provider_error_returns_failure(
    committing_app: FastAPI, settings: Settings
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

    fake = FakeProvider(queue=[ProviderError("network borked")])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "prompt",
                provider=fake, db=db, app=committing_app, settings=settings,
            )
        assert isinstance(result, GenerationFailure)
        assert result.kind == "provider_error"
        assert "network borked" in result.message
    finally:
        await engine.dispose()
```

- [ ] **Step 3: Implement `generator.py`.**

```python
# packages/parcel-shell/src/parcel_shell/ai/generator.py
"""High-level generator pipeline: prompt → provider → zip → sandbox (retry once)."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.provider import (
    ClaudeProvider,
    PriorAttempt,
    ProviderError,
)
from parcel_shell.config import Settings
from parcel_shell.sandbox import service as sandbox_service
from parcel_shell.sandbox.models import SandboxInstall

_log = structlog.get_logger("parcel_shell.ai.generator")


@dataclass(frozen=True)
class GenerationFailure:
    kind: Literal["provider_error", "no_files", "gate_rejected", "exceeded_retries"]
    message: str
    gate_report: dict | None = None
    transcript: str | None = None


def _zip_files(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


async def generate_module(
    prompt: str,
    *,
    provider: ClaudeProvider,
    db: AsyncSession,
    app: FastAPI,
    settings: Settings,
    max_attempts: int = 2,
) -> SandboxInstall | GenerationFailure:
    prior: PriorAttempt | None = None
    last_report: dict | None = None
    last_transcript: str = ""

    for attempt in range(max_attempts):
        with tempfile.TemporaryDirectory() as tmp:
            working_dir = Path(tmp)
            try:
                generated = await provider.generate(prompt, working_dir, prior=prior)
            except ProviderError as exc:
                _log.info("ai.generate.provider_error", attempt=attempt, error=str(exc))
                return GenerationFailure(
                    kind="provider_error",
                    message=str(exc),
                    transcript=last_transcript or None,
                )
            last_transcript = generated.transcript
            if not generated.files:
                return GenerationFailure(
                    kind="no_files",
                    message="provider returned no files",
                    transcript=last_transcript,
                )

            zip_bytes = _zip_files(generated.files)
            try:
                row = await sandbox_service.create_sandbox(
                    db,
                    source_zip_bytes=zip_bytes,
                    app=app,
                    settings=settings,
                )
                _log.info(
                    "ai.generate.success", attempt=attempt,
                    sandbox_id=str(row.id), name=row.name,
                )
                return row
            except sandbox_service.GateRejected as exc:
                last_report = exc.report.to_dict()
                prior = PriorAttempt(
                    gate_report_json=json.dumps(last_report),
                    previous_files=generated.files,
                )
                _log.info(
                    "ai.generate.gate_rejected",
                    attempt=attempt,
                    errors=len(exc.report.errors),
                )

    return GenerationFailure(
        kind="exceeded_retries",
        message=f"gate rejected after {max_attempts} attempt(s)",
        gate_report=last_report,
        transcript=last_transcript,
    )
```

- [ ] **Step 4: Run tests.** Expected: 3 passed.

- [ ] **Step 5: Commit** — `feat(ai): generate_module orchestrator with one-turn repair`

---

### Task B3: `build_provider` + app wiring + permission

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ai/provider.py` (add `build_provider`)
- Modify: `packages/parcel-shell/src/parcel_shell/app.py` (build provider, stash on `app.state`)
- Modify: `packages/parcel-shell/src/parcel_shell/rbac/registry.py` (new `ai.generate`)
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0005_ai_permission.py`

- [ ] **Step 1: Add `build_provider`** at the bottom of `provider.py`:

```python
def build_provider(settings) -> ClaudeProvider:
    """Construct the configured provider from Settings. Returns None if the
    API provider is selected but no key is configured — caller handles that.
    """
    if settings.ai_provider == "cli":
        return ClaudeCodeCLIProvider()
    if not settings.anthropic_api_key:
        raise ValueError(
            "PARCEL_AI_PROVIDER=api requires ANTHROPIC_API_KEY to be set"
        )
    return AnthropicAPIProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )
```

- [ ] **Step 2: Wire into `create_app`.** Inside the lifespan, after settings is stashed:

```python
        try:
            app.state.ai_provider = build_provider(settings)
        except ValueError as exc:
            app.state.ai_provider = None
            log.warning("ai.provider.not_configured", reason=str(exc))
```

- [ ] **Step 3: Add `ai.generate` to `SHELL_PERMISSIONS`.**

```python
    ("ai.generate", "Generate a module draft via the Claude generator"),
```

- [ ] **Step 4: Write migration 0005.** Pattern-copy 0004 but for one permission.

```python
# 0005_ai_permission.py
"""ai.generate permission

Revision ID: 0005
Revises: 0004
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO shell.permissions (name, description, module) "
            "VALUES ('ai.generate', 'Generate a module draft via the Claude generator', 'shell') "
            "ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description"
        )
    )
    admin_id = conn.execute(
        sa.text("SELECT id FROM shell.roles WHERE name = 'admin'")
    ).scalar_one()
    conn.execute(
        sa.text(
            "INSERT INTO shell.role_permissions (role_id, permission_name) "
            "VALUES (:rid, 'ai.generate') ON CONFLICT DO NOTHING"
        ),
        {"rid": admin_id},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM shell.permissions WHERE name = 'ai.generate'"))
```

- [ ] **Step 5: Update `test_registry.py`** to include `ai.generate` in the expected set.

- [ ] **Step 6: Commit** — `feat(ai): build_provider + ai.generate permission + migration 0005`

---

## Part C — HTTP + CLI

### Task C1: HTTP admin route

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/schemas.py`
- Create: `packages/parcel-shell/src/parcel_shell/ai/router_admin.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py` (include router)
- Create: `packages/parcel-shell/tests/test_ai_routes.py`

- [ ] **Step 1: Schemas.**

```python
# schemas.py
from __future__ import annotations

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str


class GenerateFailure(BaseModel):
    kind: str
    message: str
    gate_report: dict | None = None
    transcript: str | None = None
```

- [ ] **Step 2: Router.**

```python
# router_admin.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.generator import GenerationFailure, generate_module
from parcel_shell.ai.schemas import GenerateFailure, GenerateRequest
from parcel_shell.auth.dependencies import require_permission
from parcel_shell.db import get_session
from parcel_shell.sandbox.schemas import SandboxOut

router = APIRouter(prefix="/admin/ai", tags=["admin", "ai"])


_KIND_TO_STATUS = {
    "provider_error": status.HTTP_502_BAD_GATEWAY,
    "no_files": status.HTTP_400_BAD_REQUEST,
    "gate_rejected": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "exceeded_retries": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@router.post("/generate", response_model=SandboxOut, status_code=status.HTTP_201_CREATED)
async def generate(
    body: GenerateRequest,
    request: Request,
    _: object = Depends(require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> SandboxOut:
    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI provider not configured — set ANTHROPIC_API_KEY or PARCEL_AI_PROVIDER=cli",
        )
    result = await generate_module(
        body.prompt,
        provider=provider,
        db=db,
        app=request.app,
        settings=request.app.state.settings,
    )
    if isinstance(result, GenerationFailure):
        raise HTTPException(
            status_code=_KIND_TO_STATUS.get(result.kind, status.HTTP_502_BAD_GATEWAY),
            detail=GenerateFailure(
                kind=result.kind,
                message=result.message,
                gate_report=result.gate_report,
                transcript=result.transcript,
            ).model_dump(),
        )
    return SandboxOut.model_validate(result)
```

- [ ] **Step 3: Register router in `create_app`** after the sandbox admin router:

```python
from parcel_shell.ai.router_admin import router as ai_admin_router
app.include_router(ai_admin_router)
```

- [ ] **Step 4: Write tests.** Inject a `FakeProvider` into `app.state.ai_provider` by monkeypatching before the lifespan-managed fixture, or (simpler) by `committing_app.state.ai_provider = FakeProvider(...)` inside each test.

```python
# test_ai_routes.py
from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from _fake_provider import FakeProvider

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _contacts_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for p in CONTACTS_SRC.rglob("*"):
        if "__pycache__" in p.parts or p.suffix in {".pyc"}:
            continue
        if p.is_file():
            files[str(p.relative_to(CONTACTS_SRC)).replace("\\", "/")] = p.read_bytes()
    return files


@pytest.mark.asyncio
async def test_generate_happy_path(committing_admin: AsyncClient, committing_app) -> None:
    committing_app.state.ai_provider = FakeProvider(queue=[_contacts_files()])
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "track invoices"})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "contacts"


@pytest.mark.asyncio
async def test_generate_gate_rejected_returns_422(
    committing_admin: AsyncClient, committing_app
) -> None:
    bad_files = {
        "pyproject.toml": b'[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n',
        "src/parcel_mod_bad/__init__.py": (
            b"import os\nfrom parcel_sdk import Module\n"
            b"module = Module(name='bad', version='0.1.0')\n"
        ),
    }
    committing_app.state.ai_provider = FakeProvider(queue=[bad_files, bad_files])
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "bad"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["kind"] == "exceeded_retries"
    assert detail["gate_report"] is not None


@pytest.mark.asyncio
async def test_generate_503_when_provider_unconfigured(
    committing_admin: AsyncClient, committing_app
) -> None:
    committing_app.state.ai_provider = None
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "x"})
    assert r.status_code == 503
```

- [ ] **Step 5: Commit** — `feat(ai): POST /admin/ai/generate route with failure-kind → HTTP status mapping`

---

### Task C2: CLI sub-app

**Files:**
- Create: `packages/parcel-cli/src/parcel_cli/commands/ai.py`
- Modify: `packages/parcel-cli/src/parcel_cli/main.py`
- Create: `packages/parcel-cli/tests/test_ai.py`

- [ ] **Step 1: Implement `ai.py` sub-app.**

```python
# ai.py
from __future__ import annotations

import asyncio
import typer

from parcel_cli._shell import with_shell

app = typer.Typer(
    name="ai",
    help="Parcel AI — Claude-backed module generator.",
    no_args_is_help=True,
)


@app.command("generate")
def generate(
    prompt: str = typer.Argument(..., help="Natural-language description of the module."),
) -> None:
    """Generate a module draft via the configured provider and sandbox it."""
    asyncio.run(_run(prompt))


async def _run(prompt: str) -> None:
    from parcel_shell.ai.generator import GenerationFailure, generate_module

    async with with_shell() as fast_app:
        provider = getattr(fast_app.state, "ai_provider", None)
        if provider is None:
            typer.echo(
                "error: AI provider not configured. Set ANTHROPIC_API_KEY or "
                "PARCEL_AI_PROVIDER=cli and ensure `claude` is on PATH.",
                err=True,
            )
            raise typer.Exit(2)
        sessionmaker = fast_app.state.sessionmaker
        settings = fast_app.state.settings
        async with sessionmaker() as db:
            result = await generate_module(
                prompt,
                provider=provider,
                db=db,
                app=fast_app,
                settings=settings,
            )
            await db.commit()
    if isinstance(result, GenerationFailure):
        typer.echo(f"✗ generation failed ({result.kind}): {result.message}", err=True)
        if result.gate_report is not None:
            errors = [f for f in result.gate_report["findings"] if f["severity"] == "error"]
            for f in errors[:10]:
                typer.echo(
                    f"  [{f['check']}] {f['path']}:{f['line']} {f['rule']}: {f['message']}",
                    err=True,
                )
        raise typer.Exit(1)
    typer.echo(f"✓ sandbox {result.id} at {result.url_prefix}")
```

- [ ] **Step 2: Register in `main.py`.**

```python
from parcel_cli.commands import ai as ai_cmd
# ...
app.add_typer(ai_cmd.app, name="ai")
```

- [ ] **Step 3: Write help-smoke test.**

```python
# test_ai.py
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
    assert "prompt" in result.stdout.lower() or "PROMPT" in result.stdout
```

- [ ] **Step 4: Commit** — `feat(cli): parcel ai generate subcommand`

---

## Part F — Finish

### Task F1: Full suite + CLAUDE.md + docs + merge

- [ ] **Step 1:** `uv run ruff format && uv run ruff check && uv run pyright && uv run pytest -q`. All green.

- [ ] **Step 2:** Update **CLAUDE.md**:
  - Current-phase paragraph: "Phase 7b done — Claude generator ships `POST /admin/ai/generate` + `parcel ai generate` behind a `ClaudeProvider` abstraction (API default, Claude Code CLI opt-in). One-shot with one-turn auto-repair on gate rejection. ~X-test suite. Phase 7c (chat UI) is next."
  - Roadmap: flip 7b to ✅, 7c to ⏭.
  - Locked-in decisions: add rows for the provider abstraction, the tool-use contract, the 2-attempt cap, the versioned system-prompt file, settings additions, and the kind → HTTP status mapping.

- [ ] **Step 3:** Update **README.md** — add a `parcel ai generate` quickstart block. Mention that `ANTHROPIC_API_KEY` is required for the default provider.

- [ ] **Step 4:** Update **docs/index.html** — flip 7b to ✅ in the roadmap list, add a CLI quickstart line, update the hero status line.

- [ ] **Step 5:** Update **docs/architecture.md** — new "Claude generator (Phase 7b)" section with the pipeline diagram, the two providers, the repair loop.

- [ ] **Step 6:** Commit, push, open PR, merge.

```bash
git push -u origin phase-7b-claude-generator
gh pr create --title "Phase 7b: Claude API generator" --body ...
gh pr merge --squash --delete-branch
```

---

## Self-review checklist

- [x] Provider protocol + both implementations have tests that use no network or real `claude` subprocess.
- [x] `write_file` path safety covers: absolute, `..`, Windows drive letters, disallowed extensions.
- [x] Tool-use loop has a hard iteration cap (20) to prevent runaway costs.
- [x] Per-file and total size caps (64 KiB / 1 MiB).
- [x] Orchestrator retries exactly once on gate rejection — no accidental infinite loop.
- [x] HTTP endpoint returns 503 when provider is unconfigured, 502 for provider errors, 422 for gate failures.
- [x] New `ai.generate` permission + migration 0005.
- [x] `FakeProvider` fixture reused across orchestrator, HTTP route, and (later) chat UI tests.
- [x] System prompt lives in the repo as a versioned .md file.
- [x] Settings additions don't break boot when no key is configured (generator returns 503 instead).
