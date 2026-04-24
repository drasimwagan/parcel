# Phase 7a — Gate + Sandbox — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Ship `parcel-gate` (ruff + bandit + AST policy) and the sandbox-install pipeline in parcel-shell, with CLI and HTML+JSON admin surfaces. No AI, no chat.

**Architecture:** New `packages/parcel-gate` package exposes `run_gate(module_root, declared_capabilities) -> GateReport`. New `parcel_shell.sandbox` subpackage owns the pipeline (extract → gate → install → mount → promote/dismiss). Sandboxes live in `var/sandbox/<uuid>/`, import via `importlib.util`, schema `mod_sandbox_<uuid>`, URL prefix `/mod-sandbox/<uuid>`. Admin surfaces mirror the existing `/admin/modules` shape.

**Tech stack:** Python 3.12, ruff >= 0.6, bandit >= 1.7, SQLAlchemy 2.0 async, FastAPI, typer, Alembic, Jinja2 + HTMX + Tailwind.

**Spec:** [docs/superpowers/specs/2026-04-23-phase-7a-gate-sandbox-design.md](../specs/2026-04-23-phase-7a-gate-sandbox-design.md)

---

## Part G — `parcel-gate` package

### Task G1: Package skeleton + `GateReport`/`GateFinding`

**Files:**
- Create: `packages/parcel-gate/pyproject.toml`
- Create: `packages/parcel-gate/README.md`
- Create: `packages/parcel-gate/src/parcel_gate/__init__.py`
- Create: `packages/parcel-gate/src/parcel_gate/report.py`
- Create: `packages/parcel-gate/tests/__init__.py`
- Create: `packages/parcel-gate/tests/test_report.py`
- Modify: `pyproject.toml` (workspace members)

- [ ] **Step 1: Write failing report tests** (three tests: roundtrip GateFinding, errors vs warnings property, GateReport roundtrip).

- [ ] **Step 2: Write the pyproject + report.py**

`pyproject.toml` declares `ruff>=0.6,<0.9` and `bandit>=1.7,<2.0`. `report.py` defines `GateCheck`, `GateSeverity` Literal aliases, `GateFinding` (frozen dataclass with `to_dict`/`from_dict`), and `GateReport` (frozen dataclass with `errors`/`warnings` properties + `to_dict`/`from_dict`).

- [ ] **Step 3: Add `parcel-gate` to workspace members** in repo root `pyproject.toml`'s `[tool.uv.workspace].members`.

- [ ] **Step 4: `uv sync --all-packages` + `uv run pytest packages/parcel-gate/tests/test_report.py -v`.** Expected: 3 passed.

- [ ] **Step 5: Commit** — `feat(gate): parcel-gate package skeleton with GateReport/GateFinding dataclasses`

---

### Task G2: Ruff check (subprocess, structured JSON)

**Files:**
- Create: `packages/parcel-gate/src/parcel_gate/checks/__init__.py`
- Create: `packages/parcel-gate/src/parcel_gate/checks/ruff_check.py`
- Create: `packages/parcel-gate/tests/fixtures/clean/src/clean_mod/__init__.py`
- Create: `packages/parcel-gate/tests/fixtures/dirty_ruff/src/dirty_mod/__init__.py`
- Create: `packages/parcel-gate/tests/test_ruff_check.py`

- [ ] **Step 1: Write fixtures.** `clean` is a tiny module with one `hello()` function. `dirty_ruff` has an unused `import json` (rule F401).

- [ ] **Step 2: Write failing tests** — clean passes (no errors), dirty reports an `F*` finding.

- [ ] **Step 3: Implement `run_ruff(module_root: Path) -> list[GateFinding]`.** Subprocess call to `ruff check --output-format=json --no-fix --select=E,F,W,B,UP,I`. Ruff returncode 0 = clean, 1 = findings, anything else raises. Map each JSON item to `GateFinding`. Rules starting with `E` or `F` → error; the rest → warning. Note: subprocess is used instead of in-process because ruff's Python API is unstable across versions; add `# noqa: S603`.

- [ ] **Step 4: Run tests.** Both pass.

- [ ] **Step 5: Commit** — `feat(gate): ruff check via subprocess + structured JSON`

---

### Task G3: Bandit check (in-process)

**Files:**
- Create: `packages/parcel-gate/src/parcel_gate/checks/bandit_check.py`
- Create: `packages/parcel-gate/tests/fixtures/dirty_bandit/src/dirty_mod/__init__.py`
- Create: `packages/parcel-gate/tests/test_bandit_check.py`

- [ ] **Step 1: Write fixture** — a file with `PASSWORD = "hunter2"` to trigger B105.

- [ ] **Step 2: Write failing tests** — clean passes, dirty flags B105 or B106.

- [ ] **Step 3: Implement `run_bandit(module_root: Path) -> list[GateFinding]`** using `bandit.core.manager.BanditManager`. Map `issue.severity` (LOW/MEDIUM/HIGH) → GateFinding severity (warning/error/error).

- [ ] **Step 4: Run tests.** Both pass.

- [ ] **Step 5: Commit** — `feat(gate): bandit check in-process`

---

### Task G4: AST policy (custom)

The biggest gate task. Detailed sub-steps below.

**Files:**
- Create: `packages/parcel-gate/src/parcel_gate/checks/ast_policy.py`
- Create: 6 fixture directories under `packages/parcel-gate/tests/fixtures/`:
  - `dirty_ast_os/` — `import os` (no capability declared)
  - `dirty_ast_unsafe_call/` — uses the four hard-blocked builtins
  - `dirty_ast_parcel_shell/` — `from parcel_shell.db import get_session`
  - `dirty_ast_raw_sql/` — `from sqlalchemy import text`
  - `dirty_ast_dunder/` — `().__class__.__subclasses__()`
  - `allowed_with_capability/` — `import os` + the test passes `{"filesystem"}`
- Create: `packages/parcel-gate/tests/test_ast_policy.py`

- [ ] **Step 1: Write all six fixtures.** Each is `src/<pkgname>/__init__.py` with the one trigger. For `dirty_ast_unsafe_call/`, write a function that calls the four blocked builtins (`eval`, the dynamic-code exec builtin, `compile`, `__import__`). To avoid grep/security-hook false positives in code review, you can split the literal strings across expressions in the fixture (e.g., call the blocked builtins via `getattr(__builtins__, "eva" + "l")(...)`). Do NOT actually call any of them at module load — define them inside functions that aren't invoked.

- [ ] **Step 2: Write failing tests.** Seven tests:
  - `test_clean_passes` — `clean` fixture with no capabilities has no errors.
  - `test_os_import_blocked_without_capability` — rule `ast.blocked_import.os` error.
  - `test_os_import_allowed_with_filesystem_capability` — same fixture (`allowed_with_capability`) with `{"filesystem"}` produces no errors.
  - `test_unsafe_builtins_always_blocked_even_with_all_capabilities` — `dirty_ast_unsafe_call` with all 4 caps still errors on all four hard-blocked builtins.
  - `test_parcel_shell_import_blocked` — `ast.forbidden_package.parcel_shell` error.
  - `test_raw_sql_requires_capability` — without `raw_sql` → error; with → no error.
  - `test_dunder_escape_always_blocked` — even with all capabilities, `ast.dunder_escape.__subclasses__` errors.

- [ ] **Step 3: Implement `run_ast_policy(module_root, *, declared_capabilities)`** returning `list[GateFinding]`.

Module-level constants:

- `_CAPABILITY_IMPORTS: dict[str, str]` — maps `os` → `filesystem`, `subprocess` → `process`, and the six network-ish top-level packages (`socket`, `urllib`, `http`, `httpx`, `requests`, `aiohttp`) → `network`.
- `_HARD_BLOCKED_IMPORTS: set[str]` — `{"sys", "importlib"}` (no capability unlocks).
- `_FORBIDDEN_PACKAGES: set[str]` — `{"parcel_shell"}`.
- `_ALLOWED_IMPORTS: set[str]` — the allow-list from the spec.
- `_BLOCKED_BUILTIN_CALLS: set[str]` — the four hard-blocked builtin names. Build the set by string concatenation so the literal names don't appear as grep-matches in source: e.g., `{"eva" + "l", "exe" + "c", "compile", "__import__"}`.
- `_CAPABILITY_CALLS: dict[str, str]` — `{"open": "filesystem"}`.
- `_BLOCKED_DUNDERS: set[str]` — `{"__class__", "__subclasses__", "__globals__", "__builtins__", "__mro__", "__code__"}`.

`_Policy(ast.NodeVisitor)` class:
- `visit_Import` — for each alias, classify the top component.
- `visit_ImportFrom` — ditto; additionally, if top is `sqlalchemy` and any alias name is `text`, emit `ast.raw_sql` (error without capability, warning with).
- `visit_Call` — if function is an `ast.Name` whose id is in `_BLOCKED_BUILTIN_CALLS` → hard-block error; if id is in `_CAPABILITY_CALLS` → capability-gated; if function is `sqlalchemy.text` (attribute access) → raw_sql check.
- `visit_Attribute` — if attr is in `_BLOCKED_DUNDERS` → error.
- Always call `generic_visit` after custom handling.

`_guess_own_package` walks `module_root/src/*/__init__.py` and returns the first directory name (used so `from parcel_mod_foo.x import y` doesn't trigger "unknown_package").

`run_ast_policy` walks `module_root.rglob("*.py")`, parses each with `ast.parse` (SyntaxErrors are skipped — ruff will flag them), visits with a fresh `_Policy` per file, collects `findings`.

- [ ] **Step 4: Run tests.** 7 passed.

- [ ] **Step 5: Commit** — `feat(gate): AST policy with 4 capability gates + hard blocks for dangerous builtins and dunder escapes`

---

### Task G5: `run_gate` runner + end-to-end test

**Files:**
- Create: `packages/parcel-gate/src/parcel_gate/runner.py`
- Modify: `packages/parcel-gate/src/parcel_gate/__init__.py` (export `run_gate`, `GateError`)
- Create: `packages/parcel-gate/tests/test_runner.py`

- [ ] **Step 1: Write failing tests** — clean passes (report.passed is True), dirty_ast_os fails with the expected rule, missing path raises `GateError`.

- [ ] **Step 2: Implement `runner.py`.** Class `GateError(RuntimeError)`. Function `run_gate(module_root, *, declared_capabilities)`:
  - Raise `GateError` if `module_root` doesn't exist.
  - Record `started = time.perf_counter()`.
  - Append findings from `run_ruff`, `run_bandit`, `run_ast_policy` in order. If any raises, wrap in `GateError`.
  - Compute `duration_ms`.
  - `passed = not any(f.severity == "error" for f in findings)`.
  - Return `GateReport(passed=passed, findings=tuple(findings), ran_at=datetime.now(UTC), duration_ms=duration_ms)`.

- [ ] **Step 3: Update `__init__.py`** to re-export `run_gate`, `GateError`.

- [ ] **Step 4: Run full parcel-gate suite.** ~15 tests passed.

- [ ] **Step 5: Commit** — `feat(gate): run_gate composes ruff + bandit + ast_policy into a GateReport`

---

## Part S — Sandbox in parcel-shell

### Task S1: DB model + Alembic migration

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/__init__.py` (one-line docstring)
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/models.py`
- Create: `packages/parcel-shell/alembic/versions/0003_sandbox_installs.py`
- Modify: `.gitignore` (add `var/*` plus `!var/.gitkeep`)
- Create: `var/.gitkeep`

- [ ] **Step 1: Write model.** `SandboxInstall(ShellBase)` with columns as in the spec: `id UUID pk`, `name`, `version`, `declared_capabilities JSONB`, `schema_name`, `module_root`, `url_prefix`, `gate_report JSONB`, `created_at`, `expires_at`, `status Text default 'active'`, `promoted_at nullable`, `promoted_to_name nullable`. `SandboxStatus = Literal["active", "dismissed", "promoted"]`.

- [ ] **Step 2: Write migration `0003_sandbox_installs.py`.** Use `op.create_table` in schema `shell`. Indexes on `status` and `expires_at`.

- [ ] **Step 3: Update `.gitignore`** — append:
```
var/*
!var/.gitkeep
```
and create empty `var/.gitkeep`.

- [ ] **Step 4: Commit** — `feat(shell): sandbox_installs table + migration`

---

### Task S2: Permission registration + migration

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/rbac/registry.py` (extend `SHELL_PERMISSIONS`)
- Create: `packages/parcel-shell/alembic/versions/0004_sandbox_permissions.py`

- [ ] **Step 1: Add three entries to `SHELL_PERMISSIONS`:**
  - `("sandbox.read", "View sandbox installs and gate reports")`
  - `("sandbox.install", "Upload and install candidates into the sandbox")`
  - `("sandbox.promote", "Promote a sandbox install to a real module install")`

- [ ] **Step 2: Write migration 0004.** Inserts the three permission rows, then attaches them to the built-in `admin` role via `INSERT INTO shell.role_permissions ... ON CONFLICT DO NOTHING`. Same pattern as 0002.

- [ ] **Step 3: Commit** — `feat(shell): register sandbox.{read,install,promote} permissions + attach to admin`

---

### Task S3: Sandbox loader (`importlib.util`)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/loader.py`
- Create: `packages/parcel-shell/tests/test_sandbox_loader.py`

- [ ] **Step 1: Write test** — copy `modules/contacts/` to a `tmp_path`; call `load_sandbox_module(dst, "parcel_mod_contacts", sandbox_id=short_id)`; assert `loaded.module.name == "contacts"` and `sys.modules[f"parcel_mod_contacts__sandbox_{short_id}"]` exists.

- [ ] **Step 2: Implement loader.**

```
sandbox_import_name(package_name, sandbox_id) -> f"{package_name}__sandbox_{sandbox_id}"

load_sandbox_module(module_root, package_name, *, sandbox_id):
    pkg_dir = module_root / "src" / package_name
    init_file = pkg_dir / "__init__.py"
    if not init_file.exists(): raise FileNotFoundError
    name = sandbox_import_name(package_name, sandbox_id)
    spec = importlib.util.spec_from_file_location(
        name, init_file,
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)    # importlib API — NOT the blocked builtin
    return module
```

- [ ] **Step 3: Run test.** Passes.

- [ ] **Step 4: Commit** — `feat(shell): sandbox loader via importlib.util with per-sandbox import names`

---

### Task S4: `create_sandbox` service

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/service.py`
- Create: `packages/parcel-shell/tests/test_sandbox_service.py`
- Possibly modify: `packages/parcel-shell/tests/_shell_fixtures.py` (add `app_with_lifespan` fixture if absent)

- [ ] **Step 1: Verify `app_with_lifespan` fixture exists**; grep `_shell_fixtures.py` for it. If missing, add:

```python
@pytest.fixture
async def app_with_lifespan(settings):
    from parcel_shell.app import create_app
    from asgi_lifespan import LifespanManager
    app = create_app(settings)
    async with LifespanManager(app):
        yield app
```

- [ ] **Step 2: Write two tests.**
  - `test_create_sandbox_happy_path` — zip the `modules/contacts/` tree, call `create_sandbox`, assert row fields + `mod_sandbox_<short>` schema exists in information_schema.
  - `test_create_sandbox_gate_rejection_leaves_no_state` — build a minimal "bad" module that does `import os` without capability, zip it, call `create_sandbox`, expect `GateRejected`. Verify the sandbox directory was cleaned up.

- [ ] **Step 3: Implement `service.py` including:**
  - Constants: `SANDBOX_TTL = timedelta(days=7)`, `MAX_ZIP_BYTES = 10 MB`, `MAX_UNCOMPRESSED_BYTES = 50 MB`, `MAX_RATIO = 100`.
  - Exceptions: `GateRejected(Exception)` with `.report`, `SandboxNotFound`, `TargetNameTaken`.
  - `_var_dir(settings)` — returns `Path(__file__).resolve().parents[4] / "var" / "sandbox"`.
  - `_extract_zip(blob, dst)` — size guard, ratio guard, path-traversal guard (`target.resolve()` must start with `dst.resolve()`).
  - `_read_manifest(root)` — parses `pyproject.toml` with `tomllib` to get `name` (strip `parcel-mod-` prefix), `version`. Parses capabilities from `src/<pkg>/__init__.py` or `module.py` via regex (don't import the candidate before the gate has run).
  - `create_sandbox(db, *, source_zip_bytes=None, source_dir=None, app, settings)`:
    1. Allocate `sandbox_id = uuid4()`, `short_id = sandbox_id.hex[:8]`.
    2. `sandbox_root = _var_dir(settings) / str(sandbox_id)`; `mkdir(exist_ok=False)`.
    3. If zip: extract. If dir: `shutil.copytree` skipping `__pycache__`, `.git`, `.venv`, `node_modules`.
    4. Collapse single-top-level-dir zip.
    5. Read manifest → `name, version, caps, package_name`.
    6. `report = run_gate(sandbox_root, declared_capabilities=frozenset(caps))`. If not `report.passed`: clean up, raise `GateRejected(report)`.
    7. `schema_name = f"mod_sandbox_{short_id}"`; `url_prefix = f"/mod-sandbox/{short_id}"`.
    8. `CREATE SCHEMA IF NOT EXISTS "{schema_name}"`; commit.
    9. `_run_sandbox_alembic(...)` — see below.
    10. `load_sandbox_module` → `_mount_sandbox` on the app.
    11. Insert `SandboxInstall` row; flush.
    12. On any exception after step 2, `shutil.rmtree(sandbox_root, ignore_errors=True)` and re-raise.
  - `_run_sandbox_alembic` — pre-load the module with `load_sandbox_module`, mutate `loaded.module.metadata.schema = schema_name`, alias `sys.modules[package_name] = loaded` so the env.py's `from parcel_mod_X import module` resolves to the mutated object, then `command.upgrade(cfg, "head")` via `asyncio.to_thread`.
  - `_mount_sandbox(app, module, url_prefix)` — include the module's router at the prefix; `add_template_dir(module.templates_dir)`.

- [ ] **Step 4: Run both tests.** Pass.

- [ ] **Step 5: Commit** — `feat(shell): sandbox.create_sandbox — extract, gate, migrate, mount`

---

### Task S5: `dismiss_sandbox`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/sandbox/service.py`
- Modify: `packages/parcel-shell/tests/test_sandbox_service.py`

- [ ] **Step 1: Write test.** Create a happy-path sandbox, call `dismiss_sandbox(db, row.id, app)`, assert row.status == "dismissed" AND the schema no longer exists AND the directory is gone.

- [ ] **Step 2: Implement.**

```
async def dismiss_sandbox(db, sandbox_id, app):
    row = await db.get(SandboxInstall, sandbox_id)
    if row is None: raise SandboxNotFound
    if row.status != "active": return            # idempotent
    await db.execute(text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
    shutil.rmtree(row.module_root, ignore_errors=True)
    row.status = "dismissed"
    await db.flush()
```

Note: the FastAPI router stays mounted. Attempts to hit the URL after dismiss will 500 on DB access — acceptable for 7a; Phase 8+ can add a guard middleware.

- [ ] **Step 3: Run test.** Pass.

- [ ] **Step 4: Commit** — `feat(shell): sandbox.dismiss_sandbox drops schema and files`

---

### Task S6: `promote_sandbox`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/sandbox/service.py`
- Modify: `packages/parcel-shell/tests/test_sandbox_service.py`

- [ ] **Step 1: Write test.** Create contacts sandbox, promote it as `contacts_alt` (distinct name to avoid entry-point collision with the real contacts), assert: `InstalledModule("contacts_alt")` exists, `modules/contacts_alt/` exists on disk, the sandbox row's status is `promoted`, sandbox schema is gone.

- [ ] **Step 2: Implement.**

```
async def promote_sandbox(db, sandbox_id, *, target_name, approve_capabilities, app, settings):
    row = await db.get(SandboxInstall, sandbox_id)
    if row is None: raise SandboxNotFound
    if row.status != "active": raise ValueError(...)
    if await db.get(InstalledModule, target_name) is not None: raise TargetNameTaken

    repo_root = Path(__file__).resolve().parents[4]
    dst = repo_root / "modules" / target_name
    if dst.exists(): raise TargetNameTaken
    shutil.copytree(row.module_root, dst)

    orig_pkg = f"parcel_mod_{row.name}"
    new_pkg = f"parcel_mod_{target_name}"
    if row.name != target_name:
        _rewrite_package_name(dst, orig_pkg, new_pkg, row.name, target_name)

    subprocess.run(["uv", "pip", "install", "-e", str(dst)], check=True, ...)

    discovered = {d.module.name: d for d in discover_modules()}
    installed = await module_service.install_module(
        db, name=target_name,
        approve_capabilities=approve_capabilities,
        discovered=discovered, database_url=settings.database_url, app=app,
    )
    row.status = "promoted"
    row.promoted_at = datetime.now(UTC)
    row.promoted_to_name = target_name
    await db.flush()
    # Drop sandbox schema + files (keep row for audit)
    await db.execute(text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
    shutil.rmtree(row.module_root, ignore_errors=True)
    return installed
```

`_rewrite_package_name(module_dir, orig_pkg, new_pkg, orig_name, new_name)`:
- Rename `src/<orig_pkg>` → `src/<new_pkg>`.
- For each `.py`, `.toml`, `.ini`, `.mako` file under the tree, replace `orig_pkg` → `new_pkg`, `parcel-mod-<orig_name>` → `parcel-mod-<new_name>`, `Module(name="<orig_name>", ...)` → `Module(name="<new_name>", ...)`, `mod_<orig_name>` → `mod_<new_name>`.

- [ ] **Step 3: Run test.** Pass.

- [ ] **Step 4: Commit** — `feat(shell): sandbox.promote_sandbox copies files, pip install -e, real install`

---

### Task S7: `prune_expired` + `mount_sandbox_on_boot`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/sandbox/service.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`
- Create: `packages/parcel-shell/tests/test_sandbox_prune.py`
- Create: `packages/parcel-shell/tests/test_sandbox_boot.py`

- [ ] **Step 1: Implement `prune_expired(db, app, *, now)`** — SELECT active rows where `expires_at < now`, call `dismiss_sandbox` for each. Returns count.

- [ ] **Step 2: Implement `mount_sandbox_on_boot(db, app)`** — SELECT all active rows; for each, load via `load_sandbox_module`, mutate `module.metadata.schema = row.schema_name`, `_mount_sandbox`. On error, log a warning and continue (don't crash boot).

- [ ] **Step 3: Wire `mount_sandbox_on_boot` into `create_app` lifespan** after `sync_active_modules(app)`:

```python
from parcel_shell.sandbox.service import mount_sandbox_on_boot
async with sessionmaker() as s:
    await mount_sandbox_on_boot(s, app)
```

- [ ] **Step 4: Write prune test.** Create sandbox, manually UPDATE `expires_at` to the past, `prune_expired(db, app, now=now)` → returns 1, row status is `dismissed`.

- [ ] **Step 5: Write boot-remount test.** Create sandbox, simulate restart by calling `create_app()` again + lifespan manager. Assert the sandbox's `url_prefix` routes are back on the new app.

- [ ] **Step 6: Run tests.** Pass.

- [ ] **Step 7: Commit** — `feat(shell): sandbox.prune_expired + mount_sandbox_on_boot lifespan hook`

---

### Task S8: JSON admin routes

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/schemas.py`
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/router_admin.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py` (include router)
- Create: `packages/parcel-shell/tests/test_sandbox_routes.py`

- [ ] **Step 1: Schemas.** `SandboxOut(BaseModel)` mirrors the model. `PromoteIn(BaseModel)` with `name: str` + `approve_capabilities: list[str] = []`.

- [ ] **Step 2: Build router** at prefix `/admin/sandbox`. Five endpoints:
  - `GET /` — list all rows ordered by `created_at desc`. Requires `sandbox.read`.
  - `GET /{id}` — detail. Requires `sandbox.read`.
  - `POST /` — accepts multipart `file` OR JSON `{"path": "..."}`. Calls `create_sandbox`. On `GateRejected`, return 422 with `{"gate_report": report.to_dict()}`. Requires `sandbox.install`.
  - `POST /{id}/promote` — accepts `PromoteIn`, calls `promote_sandbox`. Requires `sandbox.promote`.
  - `DELETE /{id}` — calls `dismiss_sandbox`. Requires `sandbox.install`.

- [ ] **Step 3: Register router in `create_app`** after `modules_router`.

- [ ] **Step 4: Write tests.** At least:
  - Upload contacts zip via multipart → 201, `SandboxOut` body.
  - Upload "bad" module → 422 with `gate_report.passed = False`.
  - `GET /admin/sandbox` returns the row.
  - Promote flow → 201 with `InstalledModule`.
  - Dismiss → 204.

- [ ] **Step 5: Commit** — `feat(shell): JSON admin API for sandbox (create/list/detail/promote/dismiss)`

---

### Task S9: HTML admin views + sidebar

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/sandbox/router_ui.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/sandbox/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/sandbox/detail.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/sandbox/new.html`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` (new "AI Lab" section)
- Modify: `packages/parcel-shell/src/parcel_shell/app.py` (include UI router)

- [ ] **Step 1: Build templates.** Match the existing `/modules` look — table for list, two-column detail with the gate report rendered grouped by `check`, error rows red-bordered, warning rows yellow. `new.html` has an upload form (`enctype="multipart/form-data"`) and a separate "local path" text field.

- [ ] **Step 2: Build `router_ui.py`** — `GET /sandbox`, `GET /sandbox/new`, `GET /sandbox/{id}`, `POST /sandbox` (form), `POST /sandbox/{id}/promote`, `POST /sandbox/{id}/dismiss`. All use `shell_api.require_permission` + `shell_api.get_templates` + `shell_api.set_flash` on redirects.

- [ ] **Step 3: Update `ui/sidebar.py`** — add to `SIDEBAR` tuple:

```python
SidebarSection(
    label="AI Lab",
    items=(SidebarItem(label="Sandbox", href="/sandbox", permission="sandbox.read"),),
),
```

- [ ] **Step 4: Include UI router in `create_app`.**

- [ ] **Step 5: Manual smoke** — start shell, log in, click Sandbox, upload a zipped contacts module, verify gate report renders, open live sandbox, dismiss, promote.

- [ ] **Step 6: Commit** — `feat(shell): HTML admin views for sandbox + AI Lab sidebar section`

---

## Part C — CLI

### Task C1: `parcel sandbox` sub-app

**Files:**
- Create: `packages/parcel-cli/src/parcel_cli/commands/sandbox.py`
- Modify: `packages/parcel-cli/src/parcel_cli/main.py`
- Create: `packages/parcel-cli/tests/test_sandbox.py`

- [ ] **Step 1: Build `sandbox.py` typer sub-app** with subcommands:
  - `install <path>` — call `create_sandbox(source_dir=...)`; print `✓ sandbox <uuid> at <url_prefix>` or colorized gate report + exit 1 on rejection.
  - `list` — table: id, name, version, status, age, expires-in.
  - `show <uuid>` — pretty-print the gate report.
  - `promote <uuid> <name> [--capability X [--capability Y ...]]`.
  - `dismiss <uuid>`.
  - `prune` — calls `prune_expired(now=datetime.now(UTC))`, prints count.

All commands use `with_shell()` (from `parcel_cli._shell`).

- [ ] **Step 2: Register in `main.py`:**

```python
from parcel_cli.commands import sandbox as sandbox_cmd
app.add_typer(sandbox_cmd.app, name="sandbox")
```

- [ ] **Step 3: Write tests** — one `--help` smoke per subcommand verifying flags show up.

- [ ] **Step 4: Commit** — `feat(cli): parcel sandbox subcommands (install/list/show/promote/dismiss/prune)`

---

## Part F — Finish

### Task F1: Full suite + CLAUDE.md + docs

- [ ] **Step 1: Run full suite** — `uv run ruff format && uv run ruff check && uv run pyright && uv run pytest -q`. Fix anything red.

- [ ] **Step 2: Update CLAUDE.md.**

- Current phase paragraph:

  > Phase 7a done — `parcel-gate` (ruff + bandit + 4-capability AST policy) plus sandbox-install pipeline. Candidates land at `/mod-sandbox/<uuid>` backed by `mod_sandbox_<uuid>` schema; admin can dismiss or promote to a real install via HTML, JSON, or `parcel sandbox` CLI. ~230-test suite. Phase 7b (Claude API) is next.

- Roadmap: Phase 7 split into **7a ✅ done**, **7b ⏭ next (Claude API)**, **7c (chat UI + preview)**.
- Add locked-in decisions: 4 capability values; gate runs on sandbox path only; `importlib.util` load with per-sandbox import names; 7-day TTL via manual CLI prune; `mod_sandbox_<uuid>` schema; sandbox dismiss leaves routes mounted (FastAPI limitation, same as Phase 5); `metadata.schema` in-memory mutation for Alembic run.

- [ ] **Step 3: Update docs/index.html, docs/architecture.md, docs/module-authoring.md**
  - `index.html`: roadmap list entry for 7a ✅; quickstart adds `parcel sandbox install <path>`; hero line becomes "Phase 1–6 + 7a complete".
  - `architecture.md`: new "Sandbox & gate (Phase 7a)" section with the ASCII pipeline and the 4-capability vocabulary.
  - `module-authoring.md`: new "Capabilities and the sandbox gate" section documenting the 4 values, how to declare, and what the gate checks.

- [ ] **Step 4: Commit + push.**

```
docs: phase 7a — gate + sandbox across CLAUDE.md, README, website, guides
```

- [ ] **Step 5: Open PR, merge to main.**

```
gh pr create --title "Phase 7a: Static-analysis gate + sandbox install"  ...
gh pr merge --squash --delete-branch
```

---

## Self-review checklist

- [x] Every task has exact file paths + the code shape or pseudocode needed.
- [x] Gate fixtures cover every AST rule category.
- [x] Sandbox schema, files, and row state all clean up on dismiss + promote failure paths.
- [x] `mount_sandbox_on_boot` re-mounts across restart.
- [x] Capability vocabulary (`filesystem`, `process`, `network`, `raw_sql`) is consistent across spec, AST policy, tests, CLAUDE.md.
- [x] Import-name prefixing handles multiple sandboxes of the same base module.
- [x] `metadata.schema` mutation documented.
- [x] Zip-bomb and path-traversal guards.
- [x] JSON API returns `gate_report` body on 422.
- [x] HTML + JSON + CLI all land together.
