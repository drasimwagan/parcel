# Phase 7b — Claude API Generator — Design Spec

**Date:** 2026-04-23
**Status:** Drafted, awaiting user review
**Roadmap:** Phase 7 decomposed into 7a (gate + sandbox) → **7b (Claude generator)** → 7c (chat UI + preview UX).

## Goal

Given a natural-language prompt, produce a candidate module and hand it to the Phase 7a gate + sandbox pipeline. No chat UI — that's 7c. The generator is a synchronous HTTP + CLI endpoint that admins call with a prompt and get back either a sandbox row (on success) or a structured error + gate report (on failure).

## Non-goals

- No chat UI, no streaming, no multi-turn conversations. A generation attempt is one request → one response.
- No ARQ/background queue. Admin's HTTP connection holds open for the ~30-90s the generation takes. Async queueing lands in 7c where the chat UI naturally benefits from it.
- No rate limiting, per-admin billing tracking, or cost controls. Phase 7b is trusted-admin-only; hard limits become necessary in later phases if/when end users can generate.
- No prompt refinement UI ("here's what I got, tweak it"). That's 7c's job — the chat surface is the right place for refinement.
- No retraining/fine-tuning, no RAG lookup. Every prompt is stateless.

## Decisions locked in during brainstorming

| # | Decision |
|---|---|
| Q1 | Interaction shape: **one-shot with auto-repair** (up to 2 total turns). First turn drafts; if gate rejects, second turn sees the gate report and retries once. |
| Q2 | Output format: **tool use** — Claude calls `write_file(path, content)` N times, then `submit_module()` once. We accumulate the virtual filesystem in memory. |
| Q3 | API key: **env var `ANTHROPIC_API_KEY`** loaded via `Settings`, injected into a `ClaudeProvider` object. Per-admin / per-tenant keys are a later phase; service layer takes the provider as a parameter so the refactor is trivial. |
| Q4 | Model: `claude-opus-4-7`. 8192 output tokens per turn. 120s timeout per turn. No streaming. |
| Q5 | System prompt lives in the repo as a versioned markdown file (`packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md`). |
| Q6 | Two providers behind a `ClaudeProvider` interface: `AnthropicAPIProvider` (default) and `ClaudeCodeCLIProvider`. Admin picks via `PARCEL_AI_PROVIDER=api|cli`. Both providers produce files in a throwaway temp dir; nothing touches `var/sandbox/<uuid>/` until the gate has run. |

---

## Architecture

```
HTTP/CLI ──> generate_module(prompt, provider)
                    │
                    ▼
           ClaudeProvider.generate(prompt, tmp_dir, prior_error=None)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
  AnthropicAPI               ClaudeCodeCLI
  (in-process SDK,           (subprocess in tmp_dir,
   our write_file tool,       parses its JSON output)
   bounded message loop)
         │                     │
         └──────────┬──────────┘
                    ▼
          GeneratedFiles (dict[path → bytes])
                    │
                    ▼
           zip to bytes ──> create_sandbox(source_zip_bytes, ...)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
  gate_rejected          SandboxInstall row
  (first attempt)             │
         │                     │
         └─ retry once ────────┘
            with prior gate
            report attached

           ──> returns SandboxInstall | GenerationFailure
```

**Key seam:** generation is a pure function `generate_module(prompt, *, provider, db, app, settings) -> SandboxInstall | GenerationFailure`. Everything above (HTTP routes, CLI) is a thin shell. Everything below (sandbox install) is Phase 7a untouched.

---

## New package: `parcel-shell/src/parcel_shell/ai/`

```
parcel_shell/ai/
  __init__.py                          # re-exports the public surface
  provider.py                          # ClaudeProvider protocol + two implementations
  prompts/
    generate_module.md                 # system prompt (versioned)
  generator.py                         # generate_module(...) + GenerationFailure
  service.py                           # HTTP-facing wrapper: runs generator, zips, hands to create_sandbox
  schemas.py                           # Pydantic Generator{Request,Response}
  router_admin.py                      # POST /admin/ai/generate
```

**Dependencies:**

- `anthropic>=0.40` — the official Python SDK for the API provider.
- No new dep for the CLI provider — uses `subprocess` on the existing `claude` binary.

Added to `parcel-shell`'s `pyproject.toml` `[project.dependencies]`.

---

## Provider abstraction

```python
# parcel_shell/ai/provider.py

from pathlib import Path
from typing import Protocol

@dataclass(frozen=True)
class GeneratedFiles:
    files: dict[str, bytes]           # path (relative, POSIX) → content
    transcript: str                   # raw model/CLI output for observability


@dataclass(frozen=True)
class PriorAttempt:
    """Context for a repair turn."""
    gate_report_json: str             # JSON-serialized GateReport
    previous_files: dict[str, bytes]  # what the first attempt produced


class ProviderError(Exception):
    """Network failure, auth failure, model refused, tool-use contract violated."""


class ClaudeProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        working_dir: Path,
        *,
        prior: PriorAttempt | None = None,
    ) -> GeneratedFiles:
        """Produce a candidate module. ``working_dir`` is a throwaway temp directory
        the provider may write into. Must raise ``ProviderError`` if generation
        failed (no files, malformed output, network error, etc.) rather than
        returning an empty ``GeneratedFiles``.
        """
```

### AnthropicAPIProvider

```python
class AnthropicAPIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-opus-4-7",
        max_tokens: int = 8192,
        timeout_s: float = 120.0,
    ) -> None: ...
```

Uses the Anthropic SDK's `messages.create` with:

- System prompt: the contents of `prompts/generate_module.md`.
- Tools: two — `write_file(path: str, content: str)` and `submit_module()`.
- Messages: one user turn with the prompt; if `prior` is set, also a user turn describing the first attempt's gate failures.
- `stop_reason == "tool_use"` → we read the next batch of tool calls and loop until we see `submit_module`.

Safety: we refuse any `write_file` where `path` resolves outside `working_dir`, is absolute, contains `..`, or ends in executables we don't expect (`.sh`, `.exe`, `.so`, `.dll`). Content is capped at 64 KiB per file; total at 1 MiB. Over-cap → `ProviderError`.

The repair turn reuses the same `messages` history; we append `{"role": "user", "content": "<gate_report_json>"}` and re-run. Hard cap: 2 turns total per `generate()` call.

### ClaudeCodeCLIProvider

```python
class ClaudeCodeCLIProvider:
    def __init__(
        self,
        *,
        claude_path: str = "claude",
        timeout_s: float = 180.0,
    ) -> None: ...
```

Subprocess: `claude -p "<prompt>" --output-format json --dangerously-skip-permissions` (the last flag is required because the CLI is writing to a throwaway dir we've already deemed expendable — we add `noqa` for the flag and document the rationale). Runs with `cwd=working_dir`. After exit:

- Parses stdout as JSON (`--output-format json` produces a single trailing JSON object describing the session).
- Walks `working_dir` for files, stops if the tree is empty (→ `ProviderError`).
- Returns `GeneratedFiles(files={...}, transcript=stdout)`.

Repair turn (when `prior` is set): we write the gate report as `GATE_REPORT.md` inside `working_dir` before invoking, and the prompt becomes `<original_prompt>\n\nYour previous attempt failed the gate — see GATE_REPORT.md and fix.`. Claude Code's own agentic loop handles the rest.

The CLI subprocess is confined to `working_dir` by `cwd`; we don't grant network or system access beyond what `claude` itself does. Timeout on the subprocess is enforced with `asyncio.wait_for` around `asyncio.to_thread(subprocess.run, ...)`.

### Provider selection at startup

```python
# parcel_shell/ai/provider.py
def build_provider(settings: Settings) -> ClaudeProvider:
    match settings.ai_provider:
        case "api":
            return AnthropicAPIProvider(api_key=settings.anthropic_api_key, ...)
        case "cli":
            return ClaudeCodeCLIProvider()
        case other:
            raise ValueError(f"unknown PARCEL_AI_PROVIDER: {other!r}")
```

`app.state.ai_provider = build_provider(settings)` inside `create_app`. Tests inject a fake by monkeypatching `app.state.ai_provider`.

---

## Generator orchestration (`generator.py`)

```python
@dataclass(frozen=True)
class GenerationFailure:
    kind: Literal["provider_error", "no_files", "gate_rejected", "exceeded_retries"]
    message: str
    gate_report: dict | None = None   # present if kind == "gate_rejected"
    transcript: str | None = None     # provider transcript for observability


async def generate_module(
    prompt: str,
    *,
    provider: ClaudeProvider,
    db: AsyncSession,
    app: FastAPI,
    settings: Settings,
    max_attempts: int = 2,
) -> SandboxInstall | GenerationFailure:
    """High-level pipeline — provider → zip → sandbox, with one repair turn."""
    import tempfile
    from parcel_shell.sandbox import service as sandbox_service

    prior: PriorAttempt | None = None
    last_report: dict | None = None
    last_transcript: str = ""

    for attempt in range(max_attempts):
        with tempfile.TemporaryDirectory() as tmp:
            working_dir = Path(tmp)
            try:
                generated = await provider.generate(
                    prompt, working_dir, prior=prior
                )
            except ProviderError as exc:
                return GenerationFailure(
                    kind="provider_error", message=str(exc),
                    transcript=last_transcript,
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
                    db, source_zip_bytes=zip_bytes,
                    app=app, settings=settings,
                )
                return row
            except sandbox_service.GateRejected as exc:
                last_report = exc.report.to_dict()
                prior = PriorAttempt(
                    gate_report_json=json.dumps(last_report),
                    previous_files=generated.files,
                )
                # fall through to next attempt

    return GenerationFailure(
        kind="exceeded_retries",
        message=f"gate rejected after {max_attempts} attempt(s)",
        gate_report=last_report,
        transcript=last_transcript,
    )
```

`_zip_files(files: dict[str, bytes]) -> bytes` just `zipfile.ZipFile` in memory.

---

## HTTP endpoint

```
POST /admin/ai/generate
Headers: Cookie (admin session)
Body:    {"prompt": "track invoices with number, amount, date"}

Response 201:  SandboxOut (same as /admin/sandbox responses)
Response 422:  {"kind": "gate_rejected" | "exceeded_retries",
                "message": "...",
                "gate_report": {...},
                "transcript": "..."}
Response 502:  {"kind": "provider_error", "message": "..."}
Response 400:  {"kind": "no_files", "message": "..."}
```

New permission: **`ai.generate`** — added to `SHELL_PERMISSIONS`, attached to `admin` role by migration 0005.

The HTTP handler is a thin wrapper: read body, pull provider from `request.app.state.ai_provider`, call `generate_module`, translate the result into HTTP. Requires `ai.generate`.

Rate limiting: none in 7b. Admin-only by permission is the control surface.

---

## CLI

```
parcel ai generate "<prompt>"
```

New sub-app `parcel ai` with one command for now:

- `parcel ai generate <prompt>` — calls `generate_module` in-process via `with_shell()`, prints either the sandbox info (uuid + URL) or the failure kind + gate report summary. Exit 0 on success, 1 on failure.

Placed under `packages/parcel-cli/src/parcel_cli/commands/ai.py`, registered in `main.py` via `app.add_typer(ai.app, name="ai")`.

---

## The system prompt

Lives at `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` and is loaded with `importlib.resources` at `AnthropicAPIProvider.__init__`. Content structure:

1. **Role & goal** — "You are writing a Parcel module. Output must pass a strict static-analysis gate. Emit only tool calls — no prose."
2. **Reference scaffold** — a full, gate-passing module (7 files) copied verbatim from `parcel new-module` output, with comments pointing out what each file does.
3. **Tool contract** — `write_file(path, content)`: paths are relative to the module root, use POSIX separators, never absolute, never contain `..`. `submit_module()`: call exactly once when done.
4. **Capability vocabulary** — `filesystem` / `process` / `network` / `raw_sql`. "Default to declaring no capabilities. If your module needs one, declare it in `Module(capabilities=(...))` — the admin will be asked to approve at promote time."
5. **Hard rules** (what the gate will reject, no capability unlocks) — same list as Phase 7a.
6. **Allowed import list** — SDK surface + stdlib subset.
7. **Style conventions** — `from __future__ import annotations`, type hints everywhere, 100-col lines, double quotes, no `# noqa` in generated code.

Target length: 3-4k tokens. Reviewable as a plain .md file; committing it to the repo means we can version changes and bisect regressions.

---

## Observability

Every call logs one structured event via `structlog`:

```
ai.generate.complete
  prompt_hash=<sha256[:16]>
  provider=api|cli
  attempts=1|2
  total_duration_ms=...
  tokens_input=...            # api only
  tokens_output=...           # api only
  result=sandbox|failure
  failure_kind=<enum>|null
```

No raw prompt text logged by default (PII risk). Prompt hash is enough to correlate with a failure report for debugging. A later phase can add an opt-in "keep full transcripts" setting.

---

## Settings additions

```python
# parcel_shell/config.py
class Settings(BaseSettings):
    ...
    ai_provider: Literal["api", "cli"] = "api"
    anthropic_api_key: SecretStr | None = None       # required if ai_provider == "api"
    anthropic_model: str = "claude-opus-4-7"
```

Validation: if `ai_provider == "api"` and `anthropic_api_key` is `None`, `create_app` logs a warning but doesn't crash. The generator endpoint returns a 503 "generator not configured" until a key is set. This keeps shell boot resilient in dev environments that don't have a key yet.

---

## Test strategy

**~20 new tests**, split across unit and integration layers:

### Unit — provider with fakes (no network)

- `test_anthropic_provider.py`
  - Builds an `AnthropicAPIProvider` with a stubbed `anthropic.AsyncAnthropic` client, feeds scripted tool-use sequences, asserts we accumulate files correctly.
  - Rejects `write_file` with absolute path → `ProviderError`.
  - Rejects `write_file` with `..` → `ProviderError`.
  - Rejects over-size content → `ProviderError`.
  - Missing `submit_module` before `stop_reason="end_turn"` → `ProviderError`.
- `test_cli_provider.py`
  - Stubs `subprocess.run` to return a scripted JSON + prebuilt file tree, asserts we read the tree correctly.
  - Non-zero exit → `ProviderError`.
  - Empty tree → `ProviderError`.

### Unit — orchestrator with fake provider

- `test_generator.py`
  - Success on first attempt: fake provider returns a copy of the contacts module's files → `generate_module` returns a `SandboxInstall`.
  - Gate rejection then success: fake provider returns a bad module first, good module second → 2 attempts, returns `SandboxInstall`.
  - Gate rejection twice: → `GenerationFailure(kind="exceeded_retries")`.
  - Provider error: → `GenerationFailure(kind="provider_error")`.

### Integration — HTTP + CLI smoke

- `test_ai_routes.py` — `POST /admin/ai/generate` with a fake provider injected into `app.state.ai_provider` that yields contacts files. Assert 201 + sandbox row.
- `test_ai_routes.py` — same, with a fake provider that always fails → assert 422 + `gate_report` in body.
- `test_cli_ai.py` — `parcel ai generate --help` smoke; the actual generation path is covered by the unit tests.

### Fake provider utility

`tests/_fake_provider.py` (shared fixture): a `FakeProvider` with a scripted queue of responses. Used anywhere a test needs a deterministic generator.

All tests are hermetic — zero calls to the real Anthropic API, zero invocations of the real `claude` CLI.

---

## File plan

**Create:**
- `packages/parcel-shell/src/parcel_shell/ai/__init__.py`
- `packages/parcel-shell/src/parcel_shell/ai/provider.py`
- `packages/parcel-shell/src/parcel_shell/ai/generator.py`
- `packages/parcel-shell/src/parcel_shell/ai/service.py` (thin HTTP wrapper)
- `packages/parcel-shell/src/parcel_shell/ai/schemas.py`
- `packages/parcel-shell/src/parcel_shell/ai/router_admin.py`
- `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md`
- `packages/parcel-shell/src/parcel_shell/alembic/versions/0005_ai_permission.py`
- `packages/parcel-shell/tests/test_ai_provider_api.py`
- `packages/parcel-shell/tests/test_ai_provider_cli.py`
- `packages/parcel-shell/tests/test_ai_generator.py`
- `packages/parcel-shell/tests/test_ai_routes.py`
- `packages/parcel-shell/tests/_fake_provider.py`
- `packages/parcel-cli/src/parcel_cli/commands/ai.py`
- `packages/parcel-cli/tests/test_ai.py`

**Modify:**
- `packages/parcel-shell/pyproject.toml` — add `anthropic>=0.40` to runtime deps.
- `packages/parcel-shell/src/parcel_shell/config.py` — `ai_provider`, `anthropic_api_key`, `anthropic_model`.
- `packages/parcel-shell/src/parcel_shell/rbac/registry.py` — add `ai.generate`.
- `packages/parcel-shell/src/parcel_shell/app.py` — build provider, mount `/admin/ai` router.
- `packages/parcel-cli/src/parcel_cli/main.py` — register `ai` sub-app.
- `CLAUDE.md`, `docs/index.html`, `docs/architecture.md`, `docs/module-authoring.md` — document the generator + 4 capabilities flow.

---

## Rollout order (informs plan task order)

1. `ClaudeProvider` protocol + `AnthropicAPIProvider` with scripted-fixture tests (no network).
2. `ClaudeCodeCLIProvider` with subprocess mocked.
3. `generate_module` orchestrator with the fake provider.
4. System prompt (`generate_module.md`).
5. HTTP route + permission + migration.
6. CLI sub-app.
7. Config + `build_provider` + app wiring.
8. Docs + CLAUDE.md + merge.

---

## Open risks

1. **System prompt drift.** The gate rules are encoded in two places — the AST policy (Phase 7a) and the system prompt (7b). If one changes without the other, AI output starts failing the gate for reasons the prompt didn't warn Claude about. Mitigation: a CI test that parses the AST policy's blocked/allowed lists and greps the prompt file for each — fails the build if one list goes out of sync. Land this alongside the first gate-rule addition in a later phase. Flag it in a TODO in the prompt file for now.

2. **Anthropic SDK version churn.** `anthropic` is pre-1.0 and the `tool_use` message shape has evolved. Pin to `>=0.40,<1.0` and gate upgrades on the test suite passing with the scripted fixtures.

3. **`claude` CLI output format changes.** The `--output-format json` contract is documented but has changed in minor versions. The CLI provider parses defensively (uses `.get(...)` chains, falls back to walking the working dir if JSON is missing). Smoke-tests on the actual `claude` binary are not part of the suite (hermetic tests only), so a new CLI release can break us silently. Acceptable for 7b; add a nightly smoke job in a later phase.

4. **Latency.** 30-90s per generation blocks the admin's HTTP connection. If a front proxy enforces a 60s timeout, some generations will fail with a client timeout even though the server is still working. Document the expected latency in the docs; 7c's chat UI will move this to ARQ.

5. **Cost surprise.** Each attempt is ~6-10k tokens input + ~4-8k tokens output on Opus. At current Opus pricing (~$15/$75 per Mtok), two attempts is roughly $0.10-$0.30. Not a 7b concern, but flag in docs.
