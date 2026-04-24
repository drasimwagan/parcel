"""Claude provider abstraction for the Parcel module generator.

Two implementations live here:

- :class:`AnthropicAPIProvider` — raw Anthropic SDK with our own ``write_file``
  + ``submit_module`` tool-use loop. Default.
- :class:`ClaudeCodeCLIProvider` — subprocess the ``claude`` CLI in a throwaway
  working directory.

Both produce :class:`GeneratedFiles`. The orchestrator in
:mod:`parcel_shell.ai.generator` zips them and hands them to the Phase 7a
sandbox install pipeline.
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

MAX_FILE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 1 * 1024 * 1024

# Hard safety cap on the tool-use loop in the API provider. A realistic module
# takes ~6-12 tool calls; anything over 20 indicates a runaway.
_MAX_TOOL_ITERATIONS = 20


@dataclass(frozen=True)
class GeneratedFiles:
    files: dict[str, bytes]
    transcript: str


@dataclass(frozen=True)
class PriorAttempt:
    gate_report_json: str
    previous_files: dict[str, bytes]


class ProviderError(Exception):
    """Raised when the provider could not produce a usable result.

    Covers: network/auth failures, malformed tool use, path-safety violations,
    oversized content, missing ``submit_module``, subprocess exit != 0.
    """


class ClaudeProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        working_dir: Path,
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles: ...


# ---------------------------------------------------------------------------
# AnthropicAPIProvider
# ---------------------------------------------------------------------------


def _load_system_prompt() -> str:
    from parcel_shell.ai import prompts

    return resources.files(prompts).joinpath("generate_module.md").read_text(encoding="utf-8")


_TOOLS: list[dict[str, Any]] = [
    {
        "name": "write_file",
        "description": (
            "Write a file into the module root. Paths must be relative POSIX "
            "paths without '..' segments. Call once per file."
        ),
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


def _validate_path(path: str) -> None:
    if not path:
        raise ProviderError("write_file path is empty")
    if path.startswith("/") or path.startswith("\\"):
        raise ProviderError(f"write_file path must not be absolute: {path!r}")
    if len(path) > 1 and path[1] == ":":
        raise ProviderError(f"write_file path must not be absolute: {path!r}")
    normalized = path.replace("\\", "/").split("/")
    if any(part == ".." for part in normalized):
        raise ProviderError(f"write_file path has '..' traversal: {path!r}")
    if any(path.lower().endswith(ext) for ext in (".sh", ".exe", ".so", ".dll", ".dylib")):
        raise ProviderError(f"write_file path has disallowed extension: {path!r}")


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
        working_dir: Path,  # noqa: ARG002 — API provider doesn't use the dir
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles:
        system = _load_system_prompt()
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        if prior is not None:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous attempt failed the static gate. Fix the "
                        "issues in the gate report below and emit a corrected "
                        "full module via write_file + submit_module.\n\n" + prior.gate_report_json
                    ),
                }
            )

        files: dict[str, bytes] = {}
        total_bytes = 0
        transcript_parts: list[str] = []
        submitted = False

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=_TOOLS,
                messages=messages,
            )
            transcript_parts.append(f"stop_reason={response.stop_reason}")

            tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

            messages.append({"role": "assistant", "content": list(response.content)})

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                if tu.name == "submit_module":
                    submitted = True
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": "ok",
                        }
                    )
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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": "ok",
                    }
                )

            if submitted:
                break

            if response.stop_reason != "tool_use":
                raise ProviderError(
                    "model stopped "
                    f"(reason={response.stop_reason}) without calling submit_module"
                )

            messages.append({"role": "user", "content": tool_results})

        if not submitted:
            raise ProviderError("exceeded tool-use iteration cap without submit_module")
        if not files:
            raise ProviderError("submit_module called with no files written")

        return GeneratedFiles(files=files, transcript="\n".join(transcript_parts))


# ---------------------------------------------------------------------------
# ClaudeCodeCLIProvider
# ---------------------------------------------------------------------------


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
                "# Previous attempt failed the gate\n\n" + prior.gate_report_json,
                encoding="utf-8",
            )
            effective_prompt = (
                f"{prompt}\n\n"
                "Your previous attempt failed the static gate — see "
                "GATE_REPORT.md in the working directory for details. Fix "
                "the issues and produce a corrected module."
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
            raise ProviderError(f"claude CLI not found at {self._claude_path!r}") from exc

        if result.returncode != 0:
            raise ProviderError(
                f"claude CLI exit {result.returncode}: " f"{result.stderr.strip()[:500]}"
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


# ---------------------------------------------------------------------------
# Factory — called at app startup.
# ---------------------------------------------------------------------------


def build_provider(settings: Any) -> ClaudeProvider:
    """Construct the configured provider from :class:`Settings`.

    Raises ``ValueError`` if the API provider is selected but no key is
    configured — callers should catch and degrade gracefully (the shell boots
    without a provider and the ``/admin/ai/generate`` route returns 503).
    """
    if settings.ai_provider == "cli":
        return ClaudeCodeCLIProvider()
    if not settings.anthropic_api_key:
        raise ValueError("PARCEL_AI_PROVIDER=api requires ANTHROPIC_API_KEY to be set")
    return AnthropicAPIProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )
