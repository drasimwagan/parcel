# Phase 7a — Static-Analysis Gate + Sandbox Install — Design Spec

**Date:** 2026-04-23
**Status:** Drafted, awaiting user review
**Roadmap reference:** CLAUDE.md Phase 7 — "AI module generator", decomposed into 7a/7b/7c. Phase 7a covers everything **except** the AI generator itself and the chat UI; those land in 7b and 7c.

## Goal

Land the two pieces of Phase 7 that the AI generator will depend on, without any AI in the loop yet:

1. **Static-analysis gate** — given a candidate module's source tree, run `ruff` + `bandit` + a custom AST policy, produce a structured `GateReport`. The gate is the single most load-bearing safety primitive in Parcel; it has to exist and be battle-tested on human-authored test fixtures before AI output touches it in 7b.
2. **Sandbox install** — if a candidate passes the gate, install it under a sandbox schema (`mod_sandbox_<uuid>`) at a sandbox URL prefix (`/mod-sandbox/<uuid>/`), let the admin try it live, then either **promote** (copy files to `modules/`, run a fresh real install) or **dismiss** (drop schema + files).

## Non-goals

- No Claude API, no chat UI, no multi-turn refinement (those are 7b / 7c).
- No rich preview renderer (screenshots of views, sample-record generation). Admin previews by visiting the live sandbox URL directly.
- No ARQ-backed background cleanup — 7-day expiry is swept by a manual `parcel sandbox prune` command.
- No process- or container-level isolation. The sandbox shares the shell's Python process, FastAPI app, DB pool, and Redis. Logical isolation only; the gate is what prevents a sandbox module from doing damage.
- No gate on the existing trusted-install paths (`parcel install`, `POST /admin/modules/install`). They stay untouched.

## Decisions locked in during brainstorming

| # | Decision |
|---|---|
| Q1 | Phase 7 decomposes into 7a (gate + sandbox) → 7b (Claude API) → 7c (chat UI + preview UX). |
| Q2 | Sandbox isolation = same Postgres, `mod_sandbox_<uuid>` schema. |
| Q3a | Capability vocabulary: 4 values — `filesystem`, `process`, `network`, `raw_sql`. The four always-blocked builtins (`eval`, dynamic code exec, `compile`, `__import__`) plus dunder-escape attrs have no capability unlock. |
| Q3b | Gate runs on sandbox install only. Existing trusted-install paths unchanged. |
| Q4a | Two input paths: web upload (`.zip`), and CLI (`parcel sandbox install <path>`). |
| Q4b | Sandbox lifecycle: extract to `var/sandbox/<uuid>/`, load via `importlib.util`, mount at `/mod-sandbox/<uuid>`, row in `shell.sandbox_installs`. Dismiss drops schema + files. Promote copies **files only** (no data) to `modules/<name>/` then runs the real install path. 7-day expiry via manual CLI. |
| Q4c | Dynamic load via `importlib.util.spec_from_file_location` — sandbox modules are NOT `pip install -e`'d. Keeps the directory truly throwaway. |
| Q5a | Gate output = `GateReport` with `GateFinding[]`; persisted as JSON on the sandbox row. |
| Q5b | Three HTML pages + parallel JSON API; three new permissions. |
| Q5c | HTML + JSON built together. JSON is what 7b will call in-process; HTML is what humans use. |
| Q5d | `ruff` + `bandit` run **in-process**, not subprocess. Structured findings, faster iteration. |

---

## Part 1 — The gate

### Where it lives

New top-level package: **`parcel-gate`** under `packages/parcel-gate/`. Separate from `parcel-shell` because (a) it has its own dep set (`ruff`, `bandit`) that the shell doesn't need for non-AI workflows, and (b) 7b's CLI-driven generator might want to call it without booting the shell.

```
packages/parcel-gate/
  pyproject.toml                   # deps: ruff, bandit (in-process use)
  src/parcel_gate/
    __init__.py                    # re-exports run_gate, GateReport, GateFinding, GateError
    report.py                      # GateFinding, GateReport dataclasses
    runner.py                      # run_gate(path, capabilities) -> GateReport
    checks/
      __init__.py
      ruff_check.py                # in-process ruff API
      bandit_check.py              # in-process bandit.core.manager
      ast_policy.py                # ast.NodeVisitor implementing the custom policy
  tests/
    fixtures/
      clean/                       # minimal, gate-passing module
      dirty_ruff/                  # syntax error
      dirty_bandit/                # hardcoded password
      dirty_ast_os/                # imports os without filesystem capability
      dirty_ast_eval/              # uses eval (function call)
      dirty_ast_parcel_shell/      # imports from parcel_shell
      dirty_ast_raw_sql/           # uses SA text() without raw_sql capability
      dirty_ast_dunder/            # __subclasses__ escape
      allowed_with_capability/     # imports os but declares filesystem
    test_report.py
    test_ruff_check.py
    test_bandit_check.py
    test_ast_policy.py             # one test per forbidden pattern + capability-unlock case
    test_runner.py                 # end-to-end against fixture modules
```

### Public surface

```python
# parcel_gate/__init__.py
from parcel_gate.report import GateFinding, GateReport
from parcel_gate.runner import GateError, run_gate

__all__ = ["GateError", "GateFinding", "GateReport", "run_gate"]
```

```python
# parcel_gate/report.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

GateCheck = Literal["ruff", "bandit", "ast_policy"]
GateSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class GateFinding:
    check: GateCheck
    severity: GateSeverity
    path: str          # relative to module root
    line: int | None
    rule: str          # e.g. "E501", "B201", "ast.blocked_import"
    message: str

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, raw: dict) -> "GateFinding": ...


@dataclass(frozen=True)
class GateReport:
    passed: bool
    findings: tuple[GateFinding, ...]
    ran_at: datetime
    duration_ms: int

    @property
    def errors(self) -> tuple[GateFinding, ...]: ...
    @property
    def warnings(self) -> tuple[GateFinding, ...]: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, raw: dict) -> "GateReport": ...
```

```python
# parcel_gate/runner.py
def run_gate(
    module_root: Path,
    *,
    declared_capabilities: frozenset[str],
) -> GateReport:
    """Run all three checks against the module at ``module_root``.

    Raises ``GateError`` if the gate itself could not run (file missing,
    internal tool crash). Distinct from "gate ran and found errors" — that
    returns a report with ``passed=False``.
    """
```

### Check 1 — ruff (in-process)

Use ruff's Python API against the module directory with a pinned ruleset (`E`, `F`, `W`, `B`, `UP`, `I`). Every finding becomes a `GateFinding(check="ruff", severity="error" if rule starts with E/F else "warning", …)`. Internal failures → `GateError`.

### Check 2 — bandit (in-process)

`from bandit.core import manager; b = manager.BanditManager(config, 'file')`. Feed it every `.py` file in the module, collect issues, map to `GateFinding`. Any issue at severity `MEDIUM` or higher → `error`; `LOW` → `warning`. Bandit's baseline rules cover most of what we care about; we disable the handful that are Django-specific or too noisy.

### Check 3 — AST policy (custom)

The real teeth. One `ast.NodeVisitor` walks every `.py` file. Rejects:

| Pattern | Rule id | Default | Capability that unlocks |
|---|---|---|---|
| `import os` / `from os import ...` | `ast.blocked_import.os` | error | `filesystem` |
| `import subprocess` / `from subprocess import ...` | `ast.blocked_import.subprocess` | error | `process` |
| `import socket`, `urllib`, `urllib.*`, `http.*`, `httpx`, `requests`, `aiohttp` | `ast.blocked_import.network` | error | `network` |
| `import sys` | `ast.blocked_import.sys` | error | (hard block — too powerful) |
| `import importlib` / `from importlib ...` | `ast.blocked_import.importlib` | error | (hard block) |
| `from parcel_shell...` / `import parcel_shell...` | `ast.forbidden_package.parcel_shell` | error | (hard block — Phase 6 contract) |
| Any import of a top-level package not in the allow-list | `ast.unknown_package` | warning | — |
| Calls to the four dangerous builtins: `eval`, dynamic code exec, `compile`, `__import__` | `ast.blocked_call.<name>` | error | (hard block) |
| `open(...)` calls | `ast.blocked_call.open` | error | `filesystem` |
| Attribute access: `__class__`, `__subclasses__`, `__globals__`, `__builtins__`, `__mro__`, `__code__` | `ast.dunder_escape.<attr>` | error | (hard block) |
| `sqlalchemy.text(...)` / `from sqlalchemy import text` | `ast.raw_sql` | error | `raw_sql` |
| String literal containing case-insensitive `DROP `, `TRUNCATE `, `ALTER `, `GRANT ` (word-boundary) inside a function body | `ast.sql_in_string` | warning | — |

**Allow-list for imports:** `parcel_sdk`, `parcel_sdk.*`, `fastapi`, `fastapi.*`, `starlette`, `starlette.*`, `sqlalchemy`, `sqlalchemy.*` (excluding `text`), `pydantic`, `pydantic.*`, `jinja2`, `datetime`, `uuid`, `decimal`, `enum`, `dataclasses`, `typing`, `typing_extensions`, `collections`, `collections.abc`, `itertools`, `functools`, `json`, `re`, `math`, `pathlib` (path manipulation only — `open()` still blocked), `operator`, `contextlib`, `logging`, `warnings`, the module's own top-level package (`parcel_mod_<name>`).

**Capability declaration:** read from the module's `pyproject.toml`'s `capabilities` field. If the module declares `capabilities=("filesystem",)`, `import os` downgrades from error to warning ("declared capability used"). The promote step re-confirms capabilities at install time (same pattern as the existing `install_module`).

**Warnings vs errors:** warnings populate the report but don't block. Errors block. The gate never auto-fixes.

---

## Part 2 — Sandbox install pipeline

### The pipeline

```
candidate/ (directory tree OR a .zip) ───> staging
                                              │
                                              ▼
                                         parse manifest
                                              │
                                              ▼
                                         run_gate()
                                              │
                                       pass ──┴── fail
                                        │          │
                                        ▼          ▼
                              extract to var/sandbox/<uuid>/
                              CREATE SCHEMA mod_sandbox_<uuid>
                              alembic upgrade head (schema overridden)
                              importlib.util load module
                              mount router at /mod-sandbox/<uuid>/
                              write shell.sandbox_installs row
                                        │
                                        ▼
                                   admin tries it
                                        │
                                ┌──────┴──────┐
                                ▼             ▼
                           dismiss        promote
                                │             │
                                ▼             ▼
                      DROP SCHEMA        copy files → modules/<name>/
                      rm -rf files       install_module(...)
                      delete row         dismiss sandbox
```

### Files and schema

**Runtime directory** — a new top-level `var/` gitignored. `var/sandbox/<uuid>/` is the module root for each sandbox. Survives process restart (the sandbox registry re-mounts them on boot, the same way `sync_active_modules` re-mounts regular modules).

**New shell table** — `shell.sandbox_installs`:

```python
class SandboxInstall(ShellBase):
    __tablename__ = "sandbox_installs"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]                       # from manifest
    version: Mapped[str]
    declared_capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    schema_name: Mapped[str]                # "mod_sandbox_<uuid>"
    module_root: Mapped[str]                # "var/sandbox/<uuid>"
    url_prefix: Mapped[str]                 # "/mod-sandbox/<uuid>"
    gate_report: Mapped[dict] = mapped_column(JSONB)  # serialized GateReport
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]            # created_at + 7 days
    status: Mapped[Literal["active", "dismissed", "promoted"]] = "active"
    promoted_at: Mapped[datetime | None]
    promoted_to_name: Mapped[str | None]
```

Migration: 0003_sandbox_installs.py in `parcel-shell`.

### The service layer

```python
# parcel_shell/sandbox/service.py
async def create_sandbox(
    db: AsyncSession,
    *,
    source_zip_bytes: bytes | None = None,
    source_dir: Path | None = None,
    app: FastAPI,
    settings: Settings,
) -> SandboxInstall:
    """Extract → gate → install → mount. Raises GateRejected on failure."""

async def dismiss_sandbox(db: AsyncSession, sandbox_id: UUID, app: FastAPI) -> None:
    """Drop schema, rm files, mark dismissed."""

async def promote_sandbox(
    db: AsyncSession,
    sandbox_id: UUID,
    *,
    target_name: str,
    approve_capabilities: list[str],
    app: FastAPI,
    settings: Settings,
) -> InstalledModule:
    """Copy files to modules/<name>/, pip install -e, run install_module, dismiss."""

async def prune_expired(db: AsyncSession, app: FastAPI, *, now: datetime) -> int:
    """Dismiss all sandboxes where expires_at < now AND status == 'active'. Returns count."""

async def mount_sandbox_on_boot(db: AsyncSession, app: FastAPI) -> None:
    """Lifespan hook: re-mount every status=='active' sandbox from the DB state."""
```

Errors: `GateRejected(report: GateReport)`, `SandboxNotFound`, `SandboxExpired`, `TargetNameTaken`.

### Dynamic loading without `pip install -e`

```python
# parcel_shell/sandbox/loader.py — pseudocode
def load_sandbox_module(root: Path, package_name: str):
    pkg_init = root / "src" / package_name / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        package_name, pkg_init,
        submodule_search_locations=[str(pkg_init.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)   # importlib API, not the blocked builtin
    return module
```

**Caveat:** `sys.modules[package_name] = module` means two sandboxes can't share the same `package_name`. We prefix with the sandbox UUID at load time (`parcel_mod_widgets` becomes `parcel_mod_widgets_sandbox_<short-uuid>`). The module's manifest and templates don't care — they reference paths, not the import name. Router registration uses the prefix too, so FastAPI's route table stays clean.

### Alembic on a sandbox schema

The module's `alembic.ini` points at its own `alembic/` dir and its schema is baked into `MetaData(schema="mod_<name>")`. For sandbox install we need `MetaData(schema="mod_sandbox_<uuid>")` dynamically. Two options:

1. **`SET search_path` before migration** — fragile; existing contacts migration fully-qualifies.
2. **Rewrite manifest's metadata schema at load time** — after `importlib.util` loads the module, mutate `module.metadata.schema = "mod_sandbox_<uuid>"` before calling Alembic. Surprising but clean, and only affects this process's in-memory metadata.

We go with **option 2**, documented loudly. The test fixture modules exercise both trivial and multi-migration shapes.

---

## Part 3 — Admin surfaces

### New HTML pages

- **`GET /admin/sandbox`** — list view. Columns: name, version, status, age, expires-in, gate result badge (✓ or ✗ with error count). Actions per row: "Open" (→ `/mod-sandbox/<uuid>/`), "Detail" (→ `/admin/sandbox/<uuid>`), "Dismiss".
- **`GET /admin/sandbox/new`** — upload form: `<input type="file" accept=".zip">` OR a text field for a local path. Submit → `POST /admin/sandbox`.
- **`GET /admin/sandbox/<uuid>`** — detail: manifest block (name, version, declared capabilities), gate report grouped by check with severity coloring, "Open live sandbox" link, promote form (target name + capability checkboxes), dismiss button.

### New JSON API

- `POST /admin/sandbox` — multipart (file) or JSON (path). Returns 201 + `SandboxInstall` or 422 with `{"gate_report": {...}}` on gate failure. This is the endpoint 7b's generator will call in-process.
- `GET /admin/sandbox` / `GET /admin/sandbox/<uuid>` — list/detail JSON.
- `POST /admin/sandbox/<uuid>/promote` — `{"name": "widgets", "approve_capabilities": [...]}`. Returns `InstalledModule`.
- `DELETE /admin/sandbox/<uuid>` — dismiss.

### Permissions

Migration 0004_sandbox_permissions adds three permissions and attaches them to the built-in `admin` role:

- `sandbox.read` — view listing + detail
- `sandbox.install` — upload/create
- `sandbox.promote` — promote a sandbox into a real install. `dismiss` is covered by `sandbox.install` (same risk surface).

### Sidebar

New "AI Lab" section (name future-proofs for 7b/7c) with a single **Sandbox** item under `sandbox.read`.

---

## Part 4 — CLI additions

`parcel sandbox` becomes a subcommand group:

```
parcel sandbox install <path>      # gate + install from a local module dir
parcel sandbox list                # same as GET /admin/sandbox (prints table)
parcel sandbox show <uuid>         # print gate report
parcel sandbox promote <uuid> <name> [--capability X [--capability Y ...]]
parcel sandbox dismiss <uuid>
parcel sandbox prune               # dismiss expired
```

All commands reuse `with_shell()` to boot the shell in-process (same pattern as `parcel install`/`parcel migrate`). `install` prints a colorized gate report; on failure, exit 1. On success, prints the sandbox UUID + URL.

---

## Test strategy

Approximately **35–40 new tests**:

- **`parcel-gate/tests`** — ~20 tests
  - Per-check unit tests against fixture modules (one fixture per rule).
  - `test_runner` covers the happy path and the capability-unlock flow.
  - `test_report` — serialization round-trips.
- **`parcel-shell/tests/test_sandbox_*`** — ~15 tests
  - `create_sandbox` on the contacts module (gate passes, install succeeds, router mounts).
  - `create_sandbox` on a dirty fixture (gate rejects, no DB state changed).
  - `promote_sandbox` (files copied, real install succeeds, sandbox dismissed).
  - `dismiss_sandbox`.
  - `prune_expired` with fake clock.
  - `mount_sandbox_on_boot` across process restart.
  - Integration: upload-zip happy-path through the HTTP endpoint.
- **`parcel-cli/tests`** — ~5 tests
  - Each subcommand's arg parsing + help.

The contacts module is the gold-standard fixture: real, multi-migration, uses the SDK facade cleanly, passes the gate with `capabilities=()`. Every sandbox test that needs a "good module" reuses it.

---

## File plan

**Create:**
- `packages/parcel-gate/pyproject.toml`
- `packages/parcel-gate/src/parcel_gate/{__init__,report,runner}.py`
- `packages/parcel-gate/src/parcel_gate/checks/{__init__,ruff_check,bandit_check,ast_policy}.py`
- `packages/parcel-gate/tests/fixtures/` (one subdir per scenario)
- `packages/parcel-gate/tests/{test_report,test_ruff_check,test_bandit_check,test_ast_policy,test_runner}.py`
- `packages/parcel-shell/src/parcel_shell/sandbox/{__init__,models,service,loader,schemas,router_admin,router_ui}.py`
- `packages/parcel-shell/src/parcel_shell/ui/templates/sandbox/{list,detail,new}.html`
- `packages/parcel-shell/alembic/versions/0003_sandbox_installs.py`
- `packages/parcel-shell/alembic/versions/0004_sandbox_permissions.py`
- `packages/parcel-shell/tests/test_sandbox_{service,loader,routes,prune,boot}.py`
- `packages/parcel-cli/src/parcel_cli/commands/sandbox.py` (typer sub-app)
- `packages/parcel-cli/tests/test_sandbox.py`
- `var/` directory with a `.gitkeep`; add `var/` to `.gitignore`.

**Modify:**
- `packages/parcel-shell/src/parcel_shell/app.py` — register sandbox routers, add lifespan hook.
- `packages/parcel-shell/src/parcel_shell/rbac/registry.py` — register 3 new permissions.
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` — add "AI Lab" → Sandbox entry.
- `packages/parcel-cli/src/parcel_cli/main.py` — register `sandbox` sub-app.
- `pyproject.toml` (workspace) — `parcel-gate` in members.
- `CLAUDE.md` — mark Phase 7a done; describe the decomposition; lock in the capability vocabulary and gate rules.
- `.gitignore` — add `var/`.

**Delete:** none.

---

## Open risks

1. **In-process ruff/bandit API stability.** Both tools have semi-private Python APIs; minor-version bumps could break us. Mitigation: pin exact versions in `parcel-gate/pyproject.toml` and test on upgrade.
2. **`importlib.util` sandbox loading and template resolution.** The module's `templates_dir` points at `var/sandbox/<uuid>/src/parcel_mod_<name>/templates`, which works as long as the path is absolute when passed to the Jinja `FileSystemLoader`. Test explicitly.
3. **Schema mutation via `module.metadata.schema = ...`.** This is a surprising runtime patch. Document it heavily; consider a `sandbox_schema_override` kwarg to the SDK's `run_async_migrations` helper in a later phase if it causes pain.
4. **Route collisions on re-mount.** If the process crashes mid-promote, a sandbox row might exist without its schema having been dropped. `mount_sandbox_on_boot` should tolerate and log that; the admin can manually dismiss.
5. **Large uploads.** Cap zip upload at 10 MB. Extract with zip-bomb guard (refuse if uncompressed size > 50 MB OR ratio > 100×).
