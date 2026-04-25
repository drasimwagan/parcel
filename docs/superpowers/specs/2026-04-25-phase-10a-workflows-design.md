# Phase 10a — Workflows (engine + sync triggers + minimal actions)

**Status:** approved
**Date:** 2026-04-25
**Builds on:** Phase 8 (Dashboards) for the per-module manifest pattern, Phase 9 (Reports) for the per-module-permission gating model.
**Splits into:** 10b (cron + ARQ + worker container), 10c (`send_email` / `call_webhook` / `run_module_function` / `generate_report` actions + richer UI).

## Goal

Modules declare `Workflow` objects on their manifest. The shell observes events emitted by module endpoints and runs each matching workflow's chain of actions, post-commit, in a single transaction, with an audit record per invocation. Contacts ships a `new_contact_welcome` reference workflow that stamps a `welcomed_at` field and emits a friendly audit message.

## Non-goals (10a)

- **Cron / scheduled triggers.** `OnSchedule(cron)` lands in 10b alongside ARQ.
- **ARQ + worker container.** All 10a triggers run inline post-commit. No new docker-compose service.
- **Rich actions.** `send_email`, `call_webhook`, `run_module_function`, `generate_report` land in 10c.
- **State machines.** Workflows are trigger→action chains. Named states / transitions / per-instance state are deferred. A module that genuinely needs state semantics in 10a can fake it with `update_field("state", "next")` + `OnUpdate(when_changed=("state",))` triggers.
- **Retry.** A failing action aborts the chain and writes an error audit record. No retry until 10b/ARQ provides the queue.
- **Workflow editing UI.** UI is read-only; declarations live in module code. A visual editor is a future-phase concern.
- **AI-generated workflows.** Phase 11 will extend the static-analysis gate to cover workflow declarations; not blocked by 10a.

## Locked decisions

| Area | Decision |
|---|---|
| Phase split | 10a now. 10b = cron + ARQ + worker. 10c = remaining action library + richer UI. Decomposition explicit up front (per CLAUDE.md). |
| Workflow shape | Trigger→action chain, frozen `kw_only=True` SDK dataclass. No state machines in 10a. |
| Trigger types | Three: `OnCreate(event)`, `OnUpdate(event, when_changed=())`, `Manual(event)`. All sync. |
| Action types | Two: `UpdateField(field, value)`, `EmitAudit(message)`. `value` accepts a literal or `Callable[[Ctx], Any]`. `message` is a Jinja-rendered template string with `{{ subject.* }}` access. |
| Wiring | Explicit `shell_api.emit(event, subject)` from module endpoints — not SQLAlchemy event listeners. Modules opt their writes into observation. |
| Timing | Post-commit. The shell collects emitted events on the AsyncSession via `session.info["pending_events"]`; a `after_commit` listener drains the list and dispatches workflows in a fresh session. Source transaction always succeeds independently. |
| Failure | Single transaction per chain invocation. Any action raises → chain rolls back, audit row written outside the rolled-back txn with `status="error"` + `failed_action_index`. Source write (already committed) is unaffected. No retry. |
| Audit | New shell table `shell.workflow_audit` via migration 0007 (id, created_at, module, workflow_slug, event, subject_id, status, error_message, failed_action_index, payload jsonb). |
| Permission model | Per-workflow only. `Workflow.permission` references a permission the module already owns (mirrors reports). Gates audit-view + manual-trigger together. No new shell-level `workflows.*` permissions. |
| UI surface | Three URLs: `GET /workflows` (list, grouped by module, filtered by permission), `GET /workflows/<module>/<slug>` (declaration summary + last-50 audit), `POST /workflows/<module>/<slug>/run` (manual trigger; only valid when workflow has a `Manual` trigger). Sidebar: single aggregate "Workflows" link inserted after Dashboards/Reports if user has ≥ 1 visible workflow. |
| Auth failures | Logged-out → 303 to `/login`. Missing permission or unknown workflow → 404 (consistent with dashboards / reports / AI chat). |
| SDK version | 0.5.0 → **0.6.0** (adds `Workflow`, `Trigger`, `OnCreate`, `OnUpdate`, `Manual`, `Action`, `UpdateField`, `EmitAudit`, `WorkflowContext`, plus `shell_api.emit`). |
| Contacts version | 0.3.0 → **0.4.0** (adds `welcomed_at` column via migration 0002, ships `new_contact_welcome` workflow, calls `shell_api.emit("contacts.contact.created", contact)` on POST). |

## Architecture

```
parcel_shell/
  workflows/
    __init__.py                # package marker
    models.py                  # SQLAlchemy: WorkflowAudit
    registry.py                # RegisteredWorkflow, collect_workflows, find_workflow
    runner.py                  # dispatch + chain execution + audit write
    bus.py                     # shell-side bind for shell_api.emit (collects events on session)
    router.py                  # the three HTML routes
    templates/
      workflows/
        list.html
        detail.html
        _trigger_summary.html  # human-readable rendering of triggers
        _action_summary.html   # human-readable rendering of actions
  alembic/versions/
    0007_workflow_audit.py
  ui/
    sidebar.py                 # gains _workflows_section
```

```
parcel_sdk/
  __init__.py                  # exports Workflow, Trigger types, Action types, WorkflowContext
  workflows.py                 # the dataclasses
  shell_api.py                 # gains emit(event, subject)
```

```
modules/contacts/src/parcel_mod_contacts/
  __init__.py                  # manifest gains workflows=(welcome_workflow,)
  workflows.py                 # welcome_workflow declaration
  router.py                    # gains shell_api.emit() calls on POST/PATCH
  alembic/versions/
    0002_add_welcomed_at.py
```

`mount_workflows(app, manifest)` is called from `create_app()` after `mount_reports(...)`. Like dashboards/reports, it reads `app.state.active_modules_manifest` so the existing module-activation flow Just Works.

## SDK surface

```python
# parcel_sdk/workflows.py
from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---- Triggers --------------------------------------------------------------

@dataclass(frozen=True)
class OnCreate:
    """Fires when an event whose name matches `event` is emitted."""
    event: str


@dataclass(frozen=True)
class OnUpdate:
    """Fires when an update event is emitted, optionally filtered by which
    fields changed.

    `when_changed=()` means "any change". `when_changed=("email",)` fires only
    when the `email` field is in the emitted event's `changed` list.
    """
    event: str
    when_changed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manual:
    """Fires only via POST /workflows/<module>/<slug>/run."""
    event: str  # synthetic — used for audit logging


Trigger = OnCreate | OnUpdate | Manual


# ---- Actions ---------------------------------------------------------------

@dataclass(frozen=True)
class UpdateField:
    """Set `field` on the trigger's subject row to `value`.

    `value` is either a literal (`"sent"`, `42`, `True`) or a callable that
    receives the WorkflowContext and returns the value (`lambda ctx: datetime.now(UTC)`).
    """
    field: str
    value: Any  # literal or Callable[[WorkflowContext], Any]


@dataclass(frozen=True)
class EmitAudit:
    """Write a human-readable audit message.

    `message` is a Jinja template rendered with `subject` (the event subject)
    and `event` (the event name) in scope.
    """
    message: str


Action = UpdateField | EmitAudit


# ---- Workflow declaration --------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class Workflow:
    slug: str                          # url-safe; unique per module
    title: str
    permission: str                    # module's own permission; gates audit view + manual run
    triggers: tuple[Trigger, ...]
    actions: tuple[Action, ...]
    description: str = ""              # optional human-readable summary


# ---- Runtime context -------------------------------------------------------

@dataclass(frozen=True)
class WorkflowContext:
    """Per-invocation context passed to action callables (e.g., `value=lambda ctx: ...`)."""
    session: AsyncSession              # the workflow's own short transaction
    event: str                         # e.g., "contacts.contact.created"
    subject: Any                       # the object passed to emit() — typically a SQLAlchemy model
    subject_id: UUID | None
    changed: tuple[str, ...] = ()      # only populated for OnUpdate events
```

`Module.workflows: tuple[Workflow, ...] = ()` is added to the existing `Module` dataclass.

A boot-time validation pass (in `mount_module`) warns via `structlog` if any `Workflow.permission` is not in the module's declared permission list. Mirrors the Phase-9 dashboards/reports pattern.

## Event bus

```python
# parcel_sdk/shell_api.py — adds:
async def emit(event: str, subject: Any, *, changed: tuple[str, ...] = ()) -> None:
    """Emit an event for workflow dispatch.

    Modules call this from their POST/PATCH/DELETE handlers AFTER the relevant
    DB write but BEFORE returning. The event is queued on the current session;
    workflows fire after the request session commits.
    """
    ...
```

The shell-side binding (`parcel_shell/workflows/bus.py`) implements `emit` as:

1. Resolve the current session via the existing `get_session` contextvar (same machinery `set_flash` uses).
2. Append `{"event": event, "subject": subject, "subject_id": getattr(subject, "id", None), "changed": changed}` to `session.info.setdefault("pending_events", [])`.
3. Register an `after_commit` listener on the session (idempotent — only registers once per session) that hands the queue to `runner.dispatch_events`.

`runner.dispatch_events(events)` opens a NEW session via `app.state.sessionmaker()`, looks up matching workflows, and runs each one's chain inside its own transaction. Failures are caught + audited.

Why this shape: explicit emit at endpoints makes "which write triggers a workflow" greppable; post-commit dispatch decouples source-write success from workflow success; one new session per dispatch keeps audit writes outside any rollbacks.

## Trigger matching

For each emitted event, the runner walks `collect_workflows(app)` and selects workflows where ANY trigger matches:

| Trigger type | Match condition |
|---|---|
| `OnCreate(event=E)` | emitted event name == E |
| `OnUpdate(event=E, when_changed=())` | emitted event name == E |
| `OnUpdate(event=E, when_changed=("a","b"))` | emitted event name == E **and** at least one of `a`/`b` is in `event.changed` |
| `Manual(event=E)` | never via emit; only via POST /workflows/.../run, which dispatches a synthetic event with name == E |

Multiple workflows can match the same event; they run in module-name → declaration order. Each gets its own transaction; failures don't cross-pollinate.

## Action execution

The runner opens one transaction per workflow invocation:

```python
# Pseudo-code
async with sessionmaker() as session:
    ctx = WorkflowContext(session=session, event=ev, subject=subj, subject_id=subj_id, changed=ch)
    failed_idx: int | None = None
    error: Exception | None = None
    try:
        for idx, action in enumerate(workflow.actions):
            await execute_action(action, ctx)
        await session.commit()
        status = "ok"
    except Exception as exc:
        await session.rollback()
        failed_idx = idx
        error = exc
        status = "error"
    # Audit row written in a SEPARATE session so it survives the rollback.
    async with sessionmaker() as audit_session:
        audit_session.add(WorkflowAudit(...status, failed_idx, message=str(error) if error else None...))
        await audit_session.commit()
```

`execute_action` dispatches on action type:

- **`UpdateField(field, value)`** — resolve `value` (call it with `ctx` if callable), then `setattr(ctx.subject, field, value)` and `session.add(ctx.subject)`. Note: subject is a detached instance from the originating session; the runner re-fetches by `subject_id` if present so the write hits the new session's identity map. If `subject_id` is None (e.g., manual trigger without subject), `UpdateField` raises a clear runtime error captured in audit.
- **`EmitAudit(message)`** — render `message` as Jinja with `{subject, event, ctx}` in scope; the rendered text is included in the audit row's `payload.audit_message`. No separate side effect — `EmitAudit` is for human readability of the audit log.

## Audit table

```python
# parcel_shell/workflows/models.py
from sqlalchemy import Column, Text, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, ENUM as PgEnum

class WorkflowAudit(Base):
    __tablename__ = "workflow_audit"
    __table_args__ = {"schema": "shell"}

    id: Mapped[UUID] = mapped_column(PgUUID, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    module: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_slug: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(PgUUID, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # "ok" | "error"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_action_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # payload examples:
    #   {"audit_message": "Welcomed Ada Lovelace"}                  (status=ok, EmitAudit ran)
    #   {"audit_message": "...", "updates": [{"field": "...", ...}]}  (status=ok, UpdateField + EmitAudit)
    #   {"updates_attempted": [...]}                                (status=error)
```

Index on `(module, workflow_slug, created_at desc)` for the detail page query.

## URL surface

| Method | Path | Behaviour |
|---|---|---|
| GET | `/workflows` | List page. Iterates `collect_workflows(app)`, filters by user permissions, groups by module name. Each entry shows title + trigger summary + audit-row count + last-run timestamp. |
| GET | `/workflows/<module>/<slug>` | Detail. 404 if missing or permission denied. Renders triggers + actions (human-readable Jinja partials) + last 50 audit rows. |
| POST | `/workflows/<module>/<slug>/run` | Manual run. 404 if missing / no permission / no `Manual` trigger declared. Dispatches a synthetic event whose name matches the `Manual.event` field, with `subject=None`. Redirects to detail with a flash. |

## Sidebar

`_workflows_section(request, perms)` in `parcel_shell/ui/sidebar.py`. Returns one section labelled "Workflows" with a single `SidebarItem(label="Workflows", href="/workflows")` if the user has permission for ≥ 1 declared workflow across all mounted modules. `None` otherwise. Inserted after `_reports_section`.

## Reference workflow — Contacts `new_contact_welcome`

```python
# modules/contacts/src/parcel_mod_contacts/workflows.py

from __future__ import annotations
from datetime import UTC, datetime

from parcel_sdk import (
    EmitAudit,
    OnCreate,
    UpdateField,
    Workflow,
    WorkflowContext,
)


def _now(_ctx: WorkflowContext) -> datetime:
    return datetime.now(UTC)


welcome_workflow = Workflow(
    slug="new_contact_welcome",
    title="Welcome new contact",
    permission="contacts.read",  # admin already has this; same gate dashboards uses
    triggers=(OnCreate("contacts.contact.created"),),
    actions=(
        UpdateField(field="welcomed_at", value=_now),
        EmitAudit(message="Welcomed {{ subject.first_name or subject.email }}"),
    ),
    description="Stamps `welcomed_at` and writes a friendly audit message when a contact is created.",
)
```

Manifest in `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
module = Module(
    name="contacts",
    version="0.4.0",
    permissions=(...),
    ...,
    workflows=(welcome_workflow,),
)
```

Migration 0002 in `modules/contacts/src/parcel_mod_contacts/alembic/versions/` adds:

```python
op.add_column(
    "contacts",
    sa.Column("welcomed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    schema="mod_contacts",
)
```

`Contact` model gains `welcomed_at: Mapped[datetime | None] = mapped_column(...)`.

`router.py` POST handler emits the event after the contact is committed:

```python
# (inside the existing POST handler, after db.commit())
await shell_api.emit("contacts.contact.created", new_contact)
```

## Tests

Target: ~35 new tests, ~382 total. Coverage:

**SDK** (`packages/parcel-sdk/tests/test_workflows.py`)
- `Workflow` is frozen, `kw_only=True`, requires the right fields.
- `OnCreate` / `OnUpdate` / `Manual` are frozen.
- `UpdateField` / `EmitAudit` are frozen.
- `WorkflowContext` is frozen.
- `OnUpdate.when_changed=()` defaults work.

**Module field** (`packages/parcel-sdk/tests/test_module.py`)
- `Module.workflows` defaults to `()`.
- Accepts a tuple of `Workflow`s.

**Bus** (`packages/parcel-shell/tests/test_workflows_bus.py`)
- `emit()` queues on `session.info["pending_events"]`.
- After-commit listener fires `runner.dispatch_events`.
- After-rollback drops the queue (no dispatch).

**Trigger matching** (`packages/parcel-shell/tests/test_workflows_runner.py`)
- `OnCreate` matches by event name.
- `OnUpdate(when_changed=())` matches any update event with the right name.
- `OnUpdate(when_changed=("email",))` only fires when "email" in `changed`.
- `Manual` never fires from emit.
- Multiple workflows on same event run in declaration order.

**Action execution**
- `UpdateField` with literal value sets the field.
- `UpdateField` with callable resolves it.
- `UpdateField` without subject_id raises and audit captures error.
- `EmitAudit` renders Jinja with `{{ subject.* }}` in scope.
- Chain runs in single txn — failure rolls back earlier `UpdateField` writes.
- Audit row always written (even on failure) via separate session.

**Routes** (`packages/parcel-shell/tests/test_workflows_routes.py`)
- `/workflows` logged-out → 303; lists only visible workflows.
- `/workflows/<m>/<s>` → 404 on missing / no permission; detail renders trigger + action summaries + audit rows.
- `POST /run` → 404 on missing `Manual` trigger; dispatches the synthetic event; flash + redirect.

**Sidebar** (`packages/parcel-shell/tests/test_workflows_sidebar.py`)
- Section appears with permission, hidden without, hidden with zero workflows.

**Boot validation** (`packages/parcel-shell/tests/test_workflows_boot_validation.py`)
- Warning emitted when `Workflow.permission` isn't in module's permissions.

**Migration** (`packages/parcel-shell/tests/test_migrations_0007.py`)
- Smoke test: upgrade applies `shell.workflow_audit`; downgrade drops it.

**Contacts integration** (`modules/contacts/tests/test_contacts_workflow_welcome.py`)
- POST `/mod/contacts/` creates a contact AND triggers the workflow.
- `contact.welcomed_at` is populated after the response returns.
- Audit row written with `status="ok"`.
- Manual trigger via `/workflows/contacts/new_contact_welcome/run` returns 404 (no `Manual` trigger declared).

## Documentation

- `docs/module-authoring.md` gains a "Workflows" section: declaring a `Workflow`, choosing triggers/actions, calling `shell_api.emit`, the post-commit timing model, the audit table, manual triggers.
- `CLAUDE.md` "Phased roadmap" — flip 10a to ✅ done, 10b to ⏭ next; add an 8-row Phase-10a block under "Locked-in decisions"; rewrite "Current phase" paragraph; update "Next" pointer.
- `docs/index.html` (the website) — flip Phase 10 to "✓ done (10a)" with a note that 10b/10c follow.

## Migration / compatibility

- One new shell migration (0007) — additive (new table, no schema changes elsewhere).
- One new contacts migration (0002) — adds nullable `welcomed_at` column. Backfill not required (existing contacts simply have `NULL`).
- SDK 0.6.0 is additive — existing `Module(...)` calls still type-check (new field defaults to `()`).
- No new shell permissions, no new shell routes mounted by default (the workflow router is always mounted but returns empty list when no workflows declared).

## Risks and follow-ups

- **`shell_api.emit` API surface.** This is the second SDK function modules call from request handlers (after `set_flash`). If we get the contract wrong (e.g., needing a `request` parameter we didn't ask for), we'll churn it in 10b. Bias: keep the signature as small as possible — `event: str, subject: Any, *, changed=()`. Resolve session via existing contextvar machinery.
- **Subject re-fetch on dispatch.** Dispatching workflows runs in a NEW session, but the action chain operates on the subject passed to `emit`. We re-`session.get(type(subject), subject_id)` to get a session-attached copy for `UpdateField`. If the row was deleted between commit and dispatch, the action raises and the audit captures the error.
- **Audit table growth.** No retention policy in 10a. A high-volume workflow can grow the table without bound. Acceptable for the MVP; 10c likely adds a `workflows.audit.retention_days` setting + cleanup task riding ARQ.
- **`OnUpdate.when_changed` requires the emitter to populate `changed`.** If a module emits `contacts.contact.updated` without supplying `changed=`, all `when_changed` filters silently match (we'd treat empty as "any change"). Documented; alternative is to require `changed` for update events, but that's a footgun for emitters.
- **Manual triggers without subject.** `POST /run` dispatches with `subject=None`; any `UpdateField` action will fail because there's no subject_id. Audit captures the error. We could refuse the POST when the workflow's actions require a subject, but the runtime error + clear audit message is cleaner than a static check that needs to inspect every action.
- **AI-generator awareness.** Phase 11's static-analysis gate will need to extend to workflows: ensure `Workflow.actions[*].field` strings refer to actual model columns, ensure `EmitAudit.message` is Jinja-safe, ensure workflow declarations are pure (no side effects in `value=` callables). Tracked alongside dashboards/reports follow-ups; not blocked by 10a.

## Open during implementation

None. All eight key questions are locked. Implementation can proceed straight to plan-writing.
