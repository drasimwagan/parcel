# Phase 10a — Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modules declare `Workflow(triggers=..., actions=...)` chains on their manifest. The shell observes `shell_api.emit(...)` calls from module endpoints and dispatches matching workflows post-commit, in a single transaction per chain, with an audit row per invocation. Contacts ships a `new_contact_welcome` reference workflow.

**Architecture:** Mirror Phases 8/9. New `parcel_shell/workflows/` package holds a registry, runner, event bus, router (3 routes), and templates. SDK gains `Workflow`/triggers/actions/context dataclasses plus a new `Module.workflows` tuple field and a new `shell_api.emit` function. New shell migration `0007_workflow_audit` creates `shell.workflow_audit`. Trigger dispatch hooks SQLAlchemy's `after_commit` event on the request session: events queued via `emit` are drained into a fresh session for action execution; failures are caught and audited. Contacts gains a `welcomed_at` column (migration 0002), a `welcome_workflow` declaration, and one new `emit()` line in its create-contact handler.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, FastAPI, Pydantic, Jinja2, Alembic, pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-04-25-phase-10a-workflows-design.md`](../specs/2026-04-25-phase-10a-workflows-design.md)

**Spec deviations (resolved here):**

1. The spec's `emit(event, subject, *, changed=())` resolves the session via a contextvar, "same machinery `set_flash` uses." That's incorrect — `set_flash(response, flash)` takes the response explicitly. Plan: `emit(session, event, subject, *, changed=())` follows the explicit-pass pattern. Modules already have `db` as a dep; threading it through is one extra arg, no contextvar setup, matches existing SDK ergonomics.
2. The spec sketches the after-commit listener on `Session` globally. Plan: register the listener once at shell startup (in `app.py` lifespan or `create_app`) via `event.listen(Session, "after_commit", _on_after_commit)`. The listener checks `session.info["pending_events"]`; absence means no work to do — listener is harmless on shell-internal sessions that never call `emit`.
3. The runner needs a sessionmaker to open a fresh session for dispatch. Plan: stash `app.state.sessionmaker` on `session.info["sessionmaker"]` inside the existing `parcel_shell.db.get_session` dep. The listener pulls it from there. AsyncSession.info is shared with the underlying sync Session, so the after_commit listener sees the same dict.

---

## File structure

### Created

| Path | Responsibility |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/workflows.py` | `Workflow` / `OnCreate` / `OnUpdate` / `Manual` / `UpdateField` / `EmitAudit` / `WorkflowContext` dataclasses |
| `packages/parcel-sdk/tests/test_workflows.py` | SDK unit tests |
| `packages/parcel-shell/src/parcel_shell/workflows/__init__.py` | package marker |
| `packages/parcel-shell/src/parcel_shell/workflows/models.py` | `WorkflowAudit` SQLAlchemy model |
| `packages/parcel-shell/src/parcel_shell/workflows/registry.py` | `RegisteredWorkflow`, `collect_workflows`, `find_workflow` |
| `packages/parcel-shell/src/parcel_shell/workflows/bus.py` | `_on_after_commit` listener, `install_after_commit_listener`, `_emit_to_session` |
| `packages/parcel-shell/src/parcel_shell/workflows/runner.py` | `execute_action`, `run_workflow`, `dispatch_events` |
| `packages/parcel-shell/src/parcel_shell/workflows/router.py` | three routes |
| `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/list.html` | list page |
| `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/detail.html` | detail page |
| `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/_trigger_summary.html` | per-trigger Jinja partial |
| `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/_action_summary.html` | per-action Jinja partial |
| `packages/parcel-shell/src/parcel_shell/alembic/versions/0007_workflow_audit.py` | migration |
| `packages/parcel-shell/tests/test_workflows_bus.py` | bus tests |
| `packages/parcel-shell/tests/test_workflows_runner.py` | runner tests |
| `packages/parcel-shell/tests/test_workflows_routes.py` | route tests |
| `packages/parcel-shell/tests/test_workflows_sidebar.py` | sidebar tests |
| `packages/parcel-shell/tests/test_workflows_boot_validation.py` | mount-time warning test |
| `packages/parcel-shell/tests/test_migrations_0007.py` | migration smoke test |
| `modules/contacts/src/parcel_mod_contacts/workflows.py` | `welcome_workflow` declaration |
| `modules/contacts/src/parcel_mod_contacts/alembic/versions/0002_add_welcomed_at.py` | migration |
| `modules/contacts/tests/test_contacts_workflow_welcome.py` | reference-workflow tests |

### Modified

| Path | Change |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/__init__.py` | export new types; bump `__version__` to `0.6.0` |
| `packages/parcel-sdk/src/parcel_sdk/module.py` | add `workflows: tuple[Workflow, ...] = ()` field |
| `packages/parcel-sdk/src/parcel_sdk/shell_api.py` | add `emit` to `ShellBinding` Protocol + module-level accessor |
| `packages/parcel-sdk/tests/test_module.py` | tests for `Module.workflows` |
| `packages/parcel-shell/src/parcel_shell/shell_api_impl.py` | implement `emit` on `DefaultShellBinding` |
| `packages/parcel-shell/src/parcel_shell/db.py` | stash `sessionmaker` on `session.info` inside `get_session` |
| `packages/parcel-shell/src/parcel_shell/app.py` | install after-commit listener; mount workflows router |
| `packages/parcel-shell/src/parcel_shell/ui/templates.py` | add `_WORKFLOWS_DIR` to choice loader |
| `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` | add `_workflows_section` and wire into `sidebar_for` |
| `packages/parcel-shell/src/parcel_shell/modules/integration.py` | boot warning for `Workflow.permission` not in module's permissions |
| `modules/contacts/src/parcel_mod_contacts/__init__.py` | bump to `0.4.0`; register workflows |
| `modules/contacts/src/parcel_mod_contacts/models.py` | add `welcomed_at` column |
| `modules/contacts/src/parcel_mod_contacts/router.py` | `await shell_api.emit(db, "contacts.contact.created", contact)` after commit on POST |
| `modules/contacts/pyproject.toml` | bump version to `0.4.0` |
| `docs/module-authoring.md` | new "Workflows" section |
| `CLAUDE.md` | flip 10a to ✅ done; add Phase-10a block to Locked-in decisions; rewrite Current phase |

---

## Task 1: SDK — workflow dataclasses

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/workflows.py`
- Create: `packages/parcel-sdk/tests/test_workflows.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-sdk/tests/test_workflows.py`:

```python
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from parcel_sdk import (
    EmitAudit,
    Manual,
    OnCreate,
    OnUpdate,
    UpdateField,
    Workflow,
    WorkflowContext,
)


def test_oncreate_is_frozen() -> None:
    t = OnCreate(event="x.y.z")
    assert t.event == "x.y.z"
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.event = "other"  # type: ignore[misc]


def test_onupdate_defaults_when_changed_empty() -> None:
    t = OnUpdate(event="x.y.z")
    assert t.when_changed == ()


def test_onupdate_with_when_changed() -> None:
    t = OnUpdate(event="x.y.z", when_changed=("email",))
    assert t.when_changed == ("email",)


def test_manual_is_frozen() -> None:
    t = Manual(event="x.y.z")
    assert t.event == "x.y.z"
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.event = "other"  # type: ignore[misc]


def test_updatefield_accepts_literal_value() -> None:
    a = UpdateField(field="email", value="x@y.com")
    assert a.field == "email"
    assert a.value == "x@y.com"


def test_updatefield_accepts_callable_value() -> None:
    a = UpdateField(field="ts", value=lambda _ctx: datetime.now(UTC))
    assert callable(a.value)


def test_emitaudit_is_frozen() -> None:
    a = EmitAudit(message="hello {{ subject.name }}")
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.message = "x"  # type: ignore[misc]


def test_workflow_is_frozen_kw_only() -> None:
    w = Workflow(
        slug="test",
        title="Test",
        permission="x.read",
        triggers=(OnCreate("x.created"),),
        actions=(EmitAudit("hi"),),
    )
    assert dataclasses.is_dataclass(w)
    with pytest.raises(dataclasses.FrozenInstanceError):
        w.title = "Other"  # type: ignore[misc]


def test_workflow_requires_kw_only() -> None:
    with pytest.raises(TypeError):
        Workflow("test", "Test", "x.read", (), ())  # type: ignore[misc]


def test_workflow_description_defaults_empty() -> None:
    w = Workflow(
        slug="test",
        title="Test",
        permission="x.read",
        triggers=(OnCreate("x.created"),),
        actions=(EmitAudit("hi"),),
    )
    assert w.description == ""


def test_workflow_context_is_frozen() -> None:
    ctx = WorkflowContext(
        session=object(),  # type: ignore[arg-type]
        event="x.y",
        subject=None,
        subject_id=None,
        changed=(),
    )
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.event = "z"  # type: ignore[misc]


def test_workflow_context_changed_defaults_empty() -> None:
    ctx = WorkflowContext(
        session=object(),  # type: ignore[arg-type]
        event="x.y",
        subject=None,
        subject_id=uuid4(),
    )
    assert ctx.changed == ()
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v
```

Expected: ImportError on `from parcel_sdk import ...`.

- [ ] **Step 3: Implement the SDK module**

`packages/parcel-sdk/src/parcel_sdk/workflows.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ---- Triggers --------------------------------------------------------------


@dataclass(frozen=True)
class OnCreate:
    """Fires when an event with the given name is emitted."""

    event: str


@dataclass(frozen=True)
class OnUpdate:
    """Fires on an update event, optionally filtered by which fields changed.

    `when_changed=()` matches any update event with the right name.
    `when_changed=("email",)` fires only when "email" is in the emitted
    `changed` list.
    """

    event: str
    when_changed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manual:
    """Fires only via POST /workflows/<module>/<slug>/run.

    The `event` is the name dispatched by the manual-trigger handler — used
    for audit logging.
    """

    event: str


Trigger = Union[OnCreate, OnUpdate, Manual]


# ---- Actions ---------------------------------------------------------------


@dataclass(frozen=True)
class UpdateField:
    """Set `field` on the trigger's subject row to `value`.

    `value` is either a literal (`"sent"`, `42`, `True`) or a
    `Callable[[WorkflowContext], Any]` that returns the value at run time.
    """

    field: str
    value: Any  # literal or Callable[[WorkflowContext], Any]


@dataclass(frozen=True)
class EmitAudit:
    """Render a Jinja `message` and store it in the audit row's payload.

    The template has `subject` (the event subject) and `event` (the event
    name) in scope.
    """

    message: str


Action = Union[UpdateField, EmitAudit]


# ---- Workflow declaration --------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Workflow:
    """A trigger-to-action chain attached to a module manifest."""

    slug: str
    title: str
    permission: str
    triggers: tuple[Trigger, ...]
    actions: tuple[Action, ...]
    description: str = ""


# ---- Runtime context -------------------------------------------------------


@dataclass(frozen=True)
class WorkflowContext:
    """Per-invocation context handed to action callables (e.g. `value=lambda ctx: now()`)."""

    session: AsyncSession
    event: str
    subject: Any
    subject_id: UUID | None
    changed: tuple[str, ...] = ()


__all__ = [
    "Action",
    "EmitAudit",
    "Manual",
    "OnCreate",
    "OnUpdate",
    "Trigger",
    "UpdateField",
    "Workflow",
    "WorkflowContext",
]
```

- [ ] **Step 4: Re-export from the SDK package and bump version**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py`. Append to imports:

```python
from parcel_sdk.workflows import (
    Action,
    EmitAudit,
    Manual,
    OnCreate,
    OnUpdate,
    Trigger,
    UpdateField,
    Workflow,
    WorkflowContext,
)
```

Add to `__all__` (alphabetically, between existing entries):

```python
    "Action",
    "EmitAudit",
    "Manual",
    "OnCreate",
    "OnUpdate",
    "Trigger",
    "UpdateField",
    "Workflow",
    "WorkflowContext",
```

Update version:

```python
__version__ = "0.6.0"
```

Update the docstring at the top:

```python
"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 10a surface: Phase 9 + workflows (Workflow, triggers, actions, WorkflowContext).
"""
```

- [ ] **Step 5: Run and verify pass**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v
```

Expected: 12 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/workflows.py \
        packages/parcel-sdk/src/parcel_sdk/__init__.py \
        packages/parcel-sdk/tests/test_workflows.py
git commit -m "feat(sdk): add Workflow + Trigger/Action types for phase 10a"
```

---

## Task 2: SDK — `Module.workflows` field

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/module.py`
- Modify: `packages/parcel-sdk/tests/test_module.py`

- [ ] **Step 1: Add failing tests**

Append to `packages/parcel-sdk/tests/test_module.py`:

```python
from parcel_sdk import EmitAudit, Module, OnCreate, Workflow


def test_module_workflows_defaults_to_empty_tuple() -> None:
    m = Module(name="demo", version="0.1.0")
    assert m.workflows == ()


def test_module_workflows_accepts_tuple() -> None:
    w = Workflow(
        slug="welcome",
        title="Welcome",
        permission="demo.read",
        triggers=(OnCreate("demo.thing.created"),),
        actions=(EmitAudit("hello"),),
    )
    m = Module(name="demo", version="0.1.0", workflows=(w,))
    assert m.workflows == (w,)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-sdk/tests/test_module.py -v -k workflows
```

Expected: TypeError on unexpected `workflows` kwarg.

- [ ] **Step 3: Add the field**

Edit `packages/parcel-sdk/src/parcel_sdk/module.py`. Inside the TYPE_CHECKING block:

```python
if TYPE_CHECKING:
    from fastapi import APIRouter  # noqa: F401
    from sqlalchemy import MetaData  # noqa: F401

    from parcel_sdk.dashboards import Dashboard
    from parcel_sdk.reports import Report
    from parcel_sdk.workflows import Workflow
```

In the `Module` dataclass body, after `reports: tuple[Report, ...] = ()`:

```python
    reports: tuple[Report, ...] = ()
    workflows: tuple[Workflow, ...] = ()
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-sdk/tests/test_module.py -v
```

Expected: all green, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/module.py packages/parcel-sdk/tests/test_module.py
git commit -m "feat(sdk): add Module.workflows tuple field"
```

---

## Task 3: SDK — `shell_api.emit`

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/shell_api.py`

- [ ] **Step 1: Update Protocol + accessor + __all__**

Edit `packages/parcel-sdk/src/parcel_sdk/shell_api.py`. Update `__all__`:

```python
__all__ = [
    "Flash",
    "FlashKind",
    "ShellBinding",
    "SidebarItem",
    "SidebarSection",
    "bind",
    "effective_permissions",
    "emit",
    "get_session",
    "get_templates",
    "require_permission",
    "set_flash",
    "sidebar_for",
]
```

Update the `ShellBinding` Protocol:

```python
class ShellBinding(Protocol):
    def get_session(self) -> Callable[..., AsyncIterator[Any]]: ...
    def require_permission(self, name: str) -> Callable[..., Awaitable[Any]]: ...
    def set_flash(self, response: Any, flash: Flash) -> None: ...
    def get_templates(self) -> Any: ...
    def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]: ...
    async def effective_permissions(self, request: Any, user: Any) -> set[str]: ...
    async def emit(
        self,
        session: Any,
        event: str,
        subject: Any,
        *,
        changed: tuple[str, ...] = (),
    ) -> None: ...
```

Add the module-level accessor after `effective_permissions`:

```python
async def emit(
    session: Any,
    event: str,
    subject: Any,
    *,
    changed: tuple[str, ...] = (),
) -> None:
    """Queue an event for workflow dispatch.

    Modules call this from their POST/PATCH handlers AFTER the relevant DB
    write but BEFORE returning. The event is queued on `session.info`;
    workflows fire after the request session commits.

    `session` is the AsyncSession the module already holds (via `Depends(shell_api.get_session())`).
    `subject` is typically a SQLAlchemy model instance whose `id` is read for `subject_id`.
    `changed` lists field names that changed (only meaningful for update events).
    """
    await _need().emit(session, event, subject, changed=changed)
```

- [ ] **Step 2: Update binding test to know the new method exists**

Check existing test (`packages/parcel-shell/tests/test_shell_api_binding.py`); typically tests just confirm `bind()` works. No edits needed unless they enumerate methods.

```bash
uv run pytest packages/parcel-sdk/tests/test_shell_api.py packages/parcel-shell/tests/test_shell_api_binding.py -v
```

Expected: existing tests still pass (they test `bind`, not the surface).

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/shell_api.py
git commit -m "feat(sdk): add shell_api.emit for workflow event dispatch"
```

---

## Task 4: Shell — migration 0007 + `WorkflowAudit` model

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0007_workflow_audit.py`
- Create: `packages/parcel-shell/src/parcel_shell/workflows/__init__.py`
- Create: `packages/parcel-shell/src/parcel_shell/workflows/models.py`
- Create: `packages/parcel-shell/tests/test_migrations_0007.py`

- [ ] **Step 1: Create the package marker**

`packages/parcel-shell/src/parcel_shell/workflows/__init__.py`:

```python
"""Shell-side workflow plumbing (registry, runner, bus, router, templates)."""
```

- [ ] **Step 2: Write the model**

`packages/parcel-shell/src/parcel_shell/workflows/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Integer, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from parcel_shell.db import Base


class WorkflowAudit(Base):
    __tablename__ = "workflow_audit"
    __table_args__ = {"schema": "shell"}

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    module: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_slug: Mapped[str] = mapped_column(Text, nullable=False)
    event: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # "ok" | "error"
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_action_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
```

(If `Base` lives elsewhere — check `packages/parcel-shell/src/parcel_shell/db.py`. If `Base` doesn't exist there, look at how `parcel_shell/auth/models.py` and `parcel_shell/rbac/models.py` declare their base. Use that exact pattern.)

- [ ] **Step 3: Inspect the most recent shell migration for style**

```bash
cat packages/parcel-shell/src/parcel_shell/alembic/versions/0006_ai_chat.py | head -30
```

Note the `revision`, `down_revision`, and the `def upgrade()` / `def downgrade()` shape.

- [ ] **Step 4: Write the migration**

`packages/parcel-shell/src/parcel_shell/alembic/versions/0007_workflow_audit.py`:

```python
"""workflow_audit table

Revision ID: 0007_workflow_audit
Revises: 0006_ai_chat
Create Date: 2026-04-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0007_workflow_audit"
down_revision = "0006_ai_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_audit",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("workflow_slug", sa.Text(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("failed_action_index", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        schema="shell",
    )
    op.create_index(
        "ix_workflow_audit_module_slug_created",
        "workflow_audit",
        ["module", "workflow_slug", sa.text("created_at DESC")],
        schema="shell",
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_audit_module_slug_created", table_name="workflow_audit", schema="shell")
    op.drop_table("workflow_audit", schema="shell")
```

- [ ] **Step 5: Write the migration smoke test**

`packages/parcel-shell/tests/test_migrations_0007.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_shell" / "alembic.ini"

pytestmark = pytest.mark.asyncio


async def test_0007_creates_workflow_audit_table(migrations_applied: str) -> None:
    eng = create_async_engine(migrations_applied, pool_pre_ping=True)
    try:
        async with eng.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names(schema="shell")
            )
            assert "workflow_audit" in tables

            cols = await conn.run_sync(
                lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("workflow_audit", schema="shell")}
            )
            assert {
                "id",
                "created_at",
                "module",
                "workflow_slug",
                "event",
                "subject_id",
                "status",
                "error_message",
                "failed_action_index",
                "payload",
            }.issubset(cols)
    finally:
        await eng.dispose()


def test_0007_downgrade_drops_table(database_url: str) -> None:
    """Apply head, downgrade by one, confirm table gone, upgrade back."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0006_ai_chat")
    # Confirm via a sync engine using a sync URL.
    from sqlalchemy import create_engine

    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    eng = create_engine(sync_url)
    try:
        with eng.connect() as conn:
            tables = inspect(conn).get_table_names(schema="shell")
            assert "workflow_audit" not in tables
    finally:
        eng.dispose()
    # restore
    command.upgrade(cfg, "head")
```

- [ ] **Step 6: Run the migration test**

```bash
uv run pytest packages/parcel-shell/tests/test_migrations_0007.py -v
```

Expected: 2 passed (testcontainers spins up a fresh Postgres; the existing `migrations_applied` and `database_url` fixtures from `_shell_fixtures.py` apply head).

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/__init__.py \
        packages/parcel-shell/src/parcel_shell/workflows/models.py \
        packages/parcel-shell/src/parcel_shell/alembic/versions/0007_workflow_audit.py \
        packages/parcel-shell/tests/test_migrations_0007.py
git commit -m "feat(shell): migration 0007 + WorkflowAudit model"
```

---

## Task 5: Shell — bus (`emit` + after-commit hook)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/bus.py`
- Modify: `packages/parcel-shell/src/parcel_shell/db.py`
- Create: `packages/parcel-shell/tests/test_workflows_bus.py`

- [ ] **Step 1: Inspect current `db.get_session`**

```bash
grep -n "async def get_session\|class.*Base\|sessionmaker" packages/parcel-shell/src/parcel_shell/db.py
```

You're looking for the FastAPI dep that yields a session per request. In `get_session`, immediately after the session is created, we'll set `session.info["sessionmaker"] = sessionmaker`.

- [ ] **Step 2: Modify `db.py`'s `get_session`**

The function currently looks something like:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

Add the `session.info` line:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker = request.app.state.sessionmaker
    async with sessionmaker() as session:
        session.info["sessionmaker"] = sessionmaker
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

(The actual function body may differ — preserve everything else; only add the `session.info["sessionmaker"] = sessionmaker` line right after `async with sessionmaker() as session:`.)

- [ ] **Step 3: Write the failing bus tests**

`packages/parcel-shell/tests/test_workflows_bus.py`:

```python
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.workflows.bus import _emit_to_session, install_after_commit_listener

pytestmark = pytest.mark.asyncio


async def test_emit_to_session_appends_to_pending_events(db_session: AsyncSession) -> None:
    await _emit_to_session(db_session, "x.y.created", subject={"id": 1}, changed=())
    assert db_session.info.get("pending_events") == [
        {"event": "x.y.created", "subject": {"id": 1}, "subject_id": None, "changed": ()}
    ]


async def test_emit_extracts_subject_id_when_present(db_session: AsyncSession) -> None:
    from uuid import uuid4

    sid = uuid4()

    class Obj:
        id = sid

    await _emit_to_session(db_session, "x.y.created", subject=Obj(), changed=())
    pending = db_session.info["pending_events"]
    assert pending[0]["subject_id"] == sid


async def test_emit_two_events_appends_in_order(db_session: AsyncSession) -> None:
    await _emit_to_session(db_session, "a", subject=None, changed=())
    await _emit_to_session(db_session, "b", subject=None, changed=("x",))
    events = db_session.info["pending_events"]
    assert [e["event"] for e in events] == ["a", "b"]
    assert events[1]["changed"] == ("x",)


def test_install_after_commit_listener_is_idempotent() -> None:
    # Calling twice doesn't raise or double-register; we use a sentinel on the
    # bus module itself.
    install_after_commit_listener()
    install_after_commit_listener()
    from parcel_shell.workflows import bus

    assert bus._listener_installed is True
```

- [ ] **Step 4: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py -v
```

Expected: ImportError.

- [ ] **Step 5: Implement `bus.py`**

`packages/parcel-shell/src/parcel_shell/workflows/bus.py`:

```python
"""Workflow event bus.

Module endpoints call ``shell_api.emit(session, event, subject)``; events are
queued on ``session.info["pending_events"]`` and dispatched in a fresh session
after the originating commit succeeds.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger("parcel_shell.workflows.bus")
_listener_installed: bool = False


async def _emit_to_session(
    session: AsyncSession,
    event_name: str,
    subject: Any,
    *,
    changed: tuple[str, ...] = (),
) -> None:
    """Append an event to the session's pending-events queue.

    The session's after_commit listener (registered by
    :func:`install_after_commit_listener`) drains and dispatches it.
    """
    pending = session.info.setdefault("pending_events", [])
    pending.append(
        {
            "event": event_name,
            "subject": subject,
            "subject_id": getattr(subject, "id", None) if subject is not None else None,
            "changed": tuple(changed),
        }
    )


def _on_after_commit(sync_session: Session) -> None:
    """SQLAlchemy after_commit listener — runs in the sync side; spawns the async dispatcher."""
    events = sync_session.info.pop("pending_events", None)
    if not events:
        return
    sessionmaker = sync_session.info.get("sessionmaker")
    if sessionmaker is None:
        # No sessionmaker on this session (shell-internal use); nothing to dispatch with.
        _log.debug("workflows.dispatch_skipped.no_sessionmaker", event_count=len(events))
        return

    # Late import to avoid a cycle (runner imports models which imports Base).
    from parcel_shell.workflows.runner import dispatch_events

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # We're not inside an async context (e.g., a sync test commit). Drop.
        _log.debug("workflows.dispatch_skipped.no_loop", event_count=len(events))
        return
    loop.create_task(dispatch_events(events, sessionmaker))


def install_after_commit_listener() -> None:
    """Register `_on_after_commit` once on the global Session class.

    Idempotent — second call is a no-op.
    """
    global _listener_installed
    if _listener_installed:
        return
    event.listen(Session, "after_commit", _on_after_commit)
    _listener_installed = True
```

- [ ] **Step 6: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/bus.py \
        packages/parcel-shell/src/parcel_shell/db.py \
        packages/parcel-shell/tests/test_workflows_bus.py
git commit -m "feat(shell): workflows event bus + after_commit dispatcher"
```

---

## Task 6: Shell — registry

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/registry.py`

(No standalone tests for the registry; covered by route + runner tests. If you prefer separate tests, mirror Phase 9's `test_reports_registry.py` shape — quick optional add.)

- [ ] **Step 1: Implement registry**

`packages/parcel-shell/src/parcel_shell/workflows/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Module, Workflow


@dataclass(frozen=True)
class RegisteredWorkflow:
    module_name: str
    workflow: Workflow


def collect_workflows(app) -> list[RegisteredWorkflow]:
    """Walk active modules' manifests and return their workflows in stable order.

    Reads ``app.state.active_modules_manifest`` (populated by ``mount_module``).
    Returns ``[]`` if state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredWorkflow] = []
    for name in sorted(manifests):
        module = manifests[name]
        for wf in module.workflows:
            out.append(RegisteredWorkflow(module_name=name, workflow=wf))
    return out


def find_workflow(
    registered: list[RegisteredWorkflow], module_name: str, slug: str
) -> RegisteredWorkflow | None:
    for r in registered:
        if r.module_name == module_name and r.workflow.slug == slug:
            return r
    return None
```

- [ ] **Step 2: Smoke-import**

```bash
uv run python -c "from parcel_shell.workflows.registry import collect_workflows, find_workflow; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/registry.py
git commit -m "feat(shell): workflow registry (collect + find)"
```

---

## Task 7: Shell — runner

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/runner.py`
- Create: `packages/parcel-shell/tests/test_workflows_runner.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_workflows_runner.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk import (
    EmitAudit,
    Manual,
    Module,
    OnCreate,
    OnUpdate,
    UpdateField,
    Workflow,
    WorkflowContext,
)
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.runner import (
    _matches,
    dispatch_events,
    execute_action,
    run_workflow,
)

pytestmark = pytest.mark.asyncio


# ---- _matches --------------------------------------------------------------


def test_matches_oncreate_by_event_name() -> None:
    assert _matches(OnCreate("x.y.created"), {"event": "x.y.created", "changed": ()})
    assert not _matches(OnCreate("x.y.created"), {"event": "z.q.created", "changed": ()})


def test_matches_onupdate_when_changed_empty_matches_any() -> None:
    assert _matches(OnUpdate("x.y.updated"), {"event": "x.y.updated", "changed": ()})
    assert _matches(OnUpdate("x.y.updated"), {"event": "x.y.updated", "changed": ("z",)})


def test_matches_onupdate_with_when_changed_filters() -> None:
    t = OnUpdate("x.y.updated", when_changed=("email",))
    assert _matches(t, {"event": "x.y.updated", "changed": ("email", "phone")})
    assert not _matches(t, {"event": "x.y.updated", "changed": ("phone",)})
    assert not _matches(t, {"event": "x.y.updated", "changed": ()})


def test_matches_manual_never_via_event() -> None:
    assert not _matches(Manual("x.y.manual"), {"event": "x.y.manual", "changed": ()})


# ---- execute_action --------------------------------------------------------


async def test_execute_action_emit_audit_renders_jinja(db_session: AsyncSession) -> None:
    class Subj:
        first_name = "Ada"

    ctx = WorkflowContext(
        session=db_session, event="x.y", subject=Subj(), subject_id=uuid.uuid4(), changed=()
    )
    payload: dict[str, Any] = {}
    await execute_action(EmitAudit(message="Welcomed {{ subject.first_name }}"), ctx, payload)
    assert payload["audit_message"] == "Welcomed Ada"


async def test_execute_action_update_field_with_literal(contacts_session: AsyncSession) -> None:
    """End-to-end UpdateField against a real Contact row."""
    from parcel_mod_contacts.models import Contact

    c = Contact(id=uuid.uuid4(), email="a@b.com", first_name="Alice")
    contacts_session.add(c)
    await contacts_session.commit()

    ctx = WorkflowContext(
        session=contacts_session,
        event="contacts.contact.created",
        subject=c,
        subject_id=c.id,
        changed=(),
    )
    payload: dict[str, Any] = {}
    await execute_action(UpdateField(field="phone", value="555"), ctx, payload)
    refreshed = await contacts_session.get(Contact, c.id)
    assert refreshed is not None
    assert refreshed.phone == "555"


async def test_execute_action_update_field_with_callable(contacts_session: AsyncSession) -> None:
    from parcel_mod_contacts.models import Contact

    c = Contact(id=uuid.uuid4(), email="a@b.com", first_name="Alice")
    contacts_session.add(c)
    await contacts_session.commit()

    ctx = WorkflowContext(
        session=contacts_session,
        event="contacts.contact.created",
        subject=c,
        subject_id=c.id,
        changed=(),
    )
    payload: dict[str, Any] = {}
    await execute_action(
        UpdateField(field="phone", value=lambda c: "callable-result"), ctx, payload
    )
    refreshed = await contacts_session.get(Contact, c.id)
    assert refreshed is not None
    assert refreshed.phone == "callable-result"


async def test_execute_action_update_field_without_subject_id_raises(
    db_session: AsyncSession,
) -> None:
    ctx = WorkflowContext(
        session=db_session, event="x.y", subject=None, subject_id=None, changed=()
    )
    payload: dict[str, Any] = {}
    with pytest.raises(RuntimeError, match="subject_id"):
        await execute_action(UpdateField(field="x", value=1), ctx, payload)


# ---- run_workflow + dispatch_events ----------------------------------------


def _audit_row_count(sync_session) -> int:
    from sqlalchemy import select

    return len(list(sync_session.execute(select(WorkflowAudit)).scalars().all()))


async def test_run_workflow_writes_ok_audit_row_for_emit_only(
    settings, sessionmaker_factory
) -> None:
    """Setup: in-memory workflow with EmitAudit only, no UpdateField, dispatched
    through run_workflow. The audit row's status should be 'ok'."""
    wf = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("x.y.created"),),
        actions=(EmitAudit("hi"),),
    )
    ev = {"event": "x.y.created", "subject": None, "subject_id": None, "changed": ()}

    await run_workflow("demo", wf, ev, sessionmaker_factory)

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].status == "ok"
        assert rows[0].module == "demo"
        assert rows[0].workflow_slug == "t"
        assert rows[0].payload.get("audit_message") == "hi"


async def test_run_workflow_audits_error_on_failing_action(
    sessionmaker_factory,
) -> None:
    wf = Workflow(
        slug="bad",
        title="Bad",
        permission="x.read",
        triggers=(OnCreate("x.y.created"),),
        actions=(
            EmitAudit("first"),
            UpdateField(field="x", value=1),  # subject is None -> RuntimeError
        ),
    )
    ev = {"event": "x.y.created", "subject": None, "subject_id": None, "changed": ()}

    await run_workflow("demo", wf, ev, sessionmaker_factory)

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].status == "error"
        assert rows[0].failed_action_index == 1
        assert rows[0].error_message is not None and "subject_id" in rows[0].error_message


async def test_dispatch_events_runs_matching_workflow_only(
    sessionmaker_factory, monkeypatch
) -> None:
    """Two workflows on different events; only the matching one fires."""
    wf_match = Workflow(
        slug="match",
        title="m",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("ran"),),
    )
    wf_skip = Workflow(
        slug="skip",
        title="s",
        permission="x.read",
        triggers=(OnCreate("b"),),
        actions=(EmitAudit("skipped"),),
    )

    class FakeApp:
        class state:
            active_modules_manifest = {
                "demo": Module(name="demo", version="0.1.0", workflows=(wf_match, wf_skip))
            }

    # Inject the fake app via the module-level reference dispatch_events expects.
    # We patch collect_workflows to read from FakeApp directly.
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", FakeApp(), raising=False)

    await dispatch_events(
        [{"event": "a", "subject": None, "subject_id": None, "changed": ()}],
        sessionmaker_factory,
    )

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].workflow_slug == "match"
```

(The fixtures `sessionmaker_factory` and the `_active_app` mechanism are introduced by this task; if your conftest doesn't ship them, see Step 3.)

- [ ] **Step 2: Add `sessionmaker_factory` fixture**

Append to `packages/parcel-shell/tests/_shell_fixtures.py` (right after `engine` or wherever sensible):

```python
@pytest.fixture
async def sessionmaker_factory(migrations_applied: str):
    """Real committing sessionmaker for runner tests that need an isolated session."""
    eng = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    try:
        yield factory
    finally:
        # Clean up audit rows we created during the test.
        async with factory() as s:
            from sqlalchemy import text as _text

            await s.execute(_text("TRUNCATE TABLE shell.workflow_audit"))
            await s.commit()
        await eng.dispose()
```

- [ ] **Step 3: Implement runner**

`packages/parcel-shell/src/parcel_shell/workflows/runner.py`:

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

import jinja2
import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from parcel_sdk import (
    EmitAudit,
    Manual,
    OnCreate,
    OnUpdate,
    UpdateField,
    Workflow,
    WorkflowContext,
)
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.registry import collect_workflows

_log = structlog.get_logger("parcel_shell.workflows.runner")
_jinja = jinja2.Environment(autoescape=False, undefined=jinja2.StrictUndefined)

# Set by `app.py` lifespan. dispatch_events reads from here to find active workflows.
_active_app: Any = None


def set_active_app(app: Any) -> None:
    """Called once at shell startup; runner uses it to discover workflows."""
    global _active_app
    _active_app = app


def _matches(trigger: Any, ev: dict) -> bool:
    """Does `trigger` match event dict `ev` (`{event, subject, subject_id, changed}`)?"""
    if isinstance(trigger, Manual):
        return False  # Manual triggers fire only via the POST /run route.
    if isinstance(trigger, OnCreate):
        return trigger.event == ev["event"]
    if isinstance(trigger, OnUpdate):
        if trigger.event != ev["event"]:
            return False
        if not trigger.when_changed:
            return True
        return any(c in trigger.when_changed for c in ev.get("changed", ()))
    return False


async def execute_action(
    action: Any, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    """Run one action against ctx, mutating payload with the outcome."""
    if isinstance(action, EmitAudit):
        rendered = _jinja.from_string(action.message).render(
            subject=ctx.subject, event=ctx.event, ctx=ctx
        )
        payload["audit_message"] = rendered
        return

    if isinstance(action, UpdateField):
        if ctx.subject_id is None:
            raise RuntimeError("UpdateField requires a subject_id; emit() supplied none")
        # Re-fetch subject in this session — the original was attached to a
        # different (already-committed) session.
        if ctx.subject is None:
            raise RuntimeError("UpdateField needs a subject of a known mapped class")
        cls = type(ctx.subject)
        attached = await ctx.session.get(cls, ctx.subject_id)
        if attached is None:
            raise RuntimeError(
                f"UpdateField target {cls.__name__}({ctx.subject_id}) no longer exists"
            )
        value = action.value(ctx) if callable(action.value) else action.value
        setattr(attached, action.field, value)
        ctx.session.add(attached)
        payload.setdefault("updates", []).append(
            {"field": action.field, "value": repr(value)}
        )
        return

    raise TypeError(f"Unknown action type: {type(action).__name__}")


async def run_workflow(
    module_name: str,
    workflow: Workflow,
    ev: dict,
    sessionmaker: async_sessionmaker,
) -> None:
    """Execute one workflow's chain in a single transaction; audit the outcome."""
    payload: dict[str, Any] = {}
    failed_idx: int | None = None
    error_message: str | None = None
    status = "ok"

    async with sessionmaker() as session:
        ctx = WorkflowContext(
            session=session,
            event=ev["event"],
            subject=ev["subject"],
            subject_id=ev["subject_id"],
            changed=ev.get("changed", ()),
        )
        try:
            for idx, action in enumerate(workflow.actions):
                await execute_action(action, ctx, payload)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            failed_idx = idx
            error_message = str(exc)
            status = "error"
            _log.warning(
                "workflows.action_failed",
                module=module_name,
                slug=workflow.slug,
                action_index=idx,
                error=error_message,
            )

    # Audit row in a separate session so it survives any chain rollback.
    async with sessionmaker() as audit_session:
        audit_session.add(
            WorkflowAudit(
                module=module_name,
                workflow_slug=workflow.slug,
                event=ev["event"],
                subject_id=ev["subject_id"],
                status=status,
                error_message=error_message,
                failed_action_index=failed_idx,
                payload=payload,
            )
        )
        await audit_session.commit()


async def dispatch_events(events: list[dict], sessionmaker: async_sessionmaker) -> None:
    """Iterate emitted events; for each, run every matching workflow."""
    if _active_app is None:
        _log.warning("workflows.dispatch_skipped.no_app", event_count=len(events))
        return
    registered = collect_workflows(_active_app)
    for ev in events:
        for r in registered:
            if any(_matches(t, ev) for t in r.workflow.triggers):
                try:
                    await run_workflow(r.module_name, r.workflow, ev, sessionmaker)
                except Exception as exc:  # noqa: BLE001
                    # Defensive — run_workflow already audits per-chain failures,
                    # but this catch ensures one bad workflow doesn't abort
                    # dispatch for siblings.
                    _log.exception(
                        "workflows.dispatch_failure",
                        module=r.module_name,
                        slug=r.workflow.slug,
                        error=str(exc),
                    )
```

- [ ] **Step 4: Run runner tests**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_runner.py -v
```

Expected: 12 passed (4 `_matches` + 4 `execute_action` + 3 `run_workflow`/`dispatch_events`).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/runner.py \
        packages/parcel-shell/tests/test_workflows_runner.py \
        packages/parcel-shell/tests/_shell_fixtures.py
git commit -m "feat(shell): workflow runner (matching, action exec, dispatch)"
```

---

## Task 8: Shell — templates + Jinja loader wiring

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/detail.html`
- Create: `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/_trigger_summary.html`
- Create: `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/_action_summary.html`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/templates.py`

- [ ] **Step 1: Write `_trigger_summary.html`**

```html
{% set t = trigger %}
{% if t.__class__.__name__ == "OnCreate" %}
  <span class="trigger-badge">on create &middot; <code>{{ t.event }}</code></span>
{% elif t.__class__.__name__ == "OnUpdate" %}
  <span class="trigger-badge">on update &middot; <code>{{ t.event }}</code>
    {% if t.when_changed %}&middot; when [{{ t.when_changed|join(", ") }}] changes{% endif %}
  </span>
{% elif t.__class__.__name__ == "Manual" %}
  <span class="trigger-badge">manual &middot; <code>{{ t.event }}</code></span>
{% else %}
  <span class="trigger-badge">{{ t.__class__.__name__ }}</span>
{% endif %}
```

- [ ] **Step 2: Write `_action_summary.html`**

```html
{% set a = action %}
{% if a.__class__.__name__ == "UpdateField" %}
  <li>set <code>{{ a.field }}</code> = {{ "callable" if a.value is callable else a.value|repr }}</li>
{% elif a.__class__.__name__ == "EmitAudit" %}
  <li>audit: <code>{{ a.message }}</code></li>
{% else %}
  <li>{{ a.__class__.__name__ }}</li>
{% endif %}
```

- [ ] **Step 3: Write `list.html`**

```html
{% extends "_base.html" %}
{% block title %}Workflows{% endblock %}
{% block content %}
<h1 class="text-xl font-semibold mb-4">Workflows</h1>
{% if not groups %}
  <p class="text-sm text-gray-500">No workflows are visible to you.</p>
{% endif %}
{% for module_name, workflows in groups %}
  <h2 class="text-md font-medium mt-4 mb-2">{{ module_name|capitalize }}</h2>
  <div class="space-y-2">
    {% for w in workflows %}
      <a href="/reports/.." style="display:none;"></a>
      <a href="/workflows/{{ module_name }}/{{ w.slug }}"
         class="block bg-white rounded shadow p-4 hover:bg-gray-50">
        <div class="flex items-baseline justify-between">
          <strong>{{ w.title }}</strong>
          <code class="text-xs text-gray-500">{{ w.slug }}</code>
        </div>
        {% if w.description %}<p class="text-sm text-gray-600 mt-1">{{ w.description }}</p>{% endif %}
        <div class="mt-2 flex gap-2 flex-wrap text-xs text-gray-500">
          {% for t in w.triggers %}
            {% include "workflows/_trigger_summary.html" %}
          {% endfor %}
        </div>
      </a>
    {% endfor %}
  </div>
{% endfor %}
{% endblock %}
```

- [ ] **Step 4: Write `detail.html`**

```html
{% extends "_base.html" %}
{% block title %}{{ workflow.title }}{% endblock %}
{% block content %}
<div class="flex items-baseline justify-between mb-4">
  <div>
    <h1 class="text-xl font-semibold">{{ workflow.title }}</h1>
    <p class="text-sm text-gray-500">{{ module_name|capitalize }} &middot; <code>{{ workflow.slug }}</code></p>
  </div>
  {% if has_manual_trigger %}
    <form method="post" action="/workflows/{{ module_name }}/{{ workflow.slug }}/run">
      <button type="submit"
              class="px-3 py-1 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700">
        Run manually
      </button>
    </form>
  {% endif %}
</div>

<div class="bg-white rounded shadow p-4 mb-4">
  {% if workflow.description %}<p class="text-sm">{{ workflow.description }}</p>{% endif %}
  <div class="mt-3 text-xs text-gray-500"><strong>Triggers:</strong></div>
  <div class="mt-1 flex gap-2 flex-wrap">
    {% for t in workflow.triggers %}
      {% include "workflows/_trigger_summary.html" %}
    {% endfor %}
  </div>
  <div class="mt-3 text-xs text-gray-500"><strong>Actions:</strong></div>
  <ol class="mt-1 list-decimal list-inside text-sm">
    {% for a in workflow.actions %}
      {% include "workflows/_action_summary.html" %}
    {% endfor %}
  </ol>
</div>

<div class="bg-white rounded shadow">
  <div class="p-4 border-b border-gray-200">
    <h2 class="text-md font-medium">Recent invocations</h2>
  </div>
  {% if not audits %}
    <p class="p-4 text-sm text-gray-500">No invocations yet.</p>
  {% else %}
    <table class="w-full text-sm">
      <thead class="bg-gray-50 text-xs uppercase text-gray-600">
        <tr>
          <th class="text-left p-2">When</th>
          <th class="text-left p-2">Event</th>
          <th class="text-left p-2">Subject</th>
          <th class="text-left p-2">Status</th>
          <th class="text-left p-2">Notes</th>
        </tr>
      </thead>
      <tbody>
        {% for a in audits %}
          <tr class="border-t border-gray-100">
            <td class="p-2">{{ a.created_at.strftime("%Y-%m-%d %H:%M:%S") }}</td>
            <td class="p-2"><code class="text-xs">{{ a.event }}</code></td>
            <td class="p-2"><code class="text-xs">{{ a.subject_id or "—" }}</code></td>
            <td class="p-2">
              {% if a.status == "ok" %}
                <span class="text-green-700">ok</span>
              {% else %}
                <span class="text-red-700">error</span>
              {% endif %}
            </td>
            <td class="p-2 text-xs">
              {% if a.error_message %}
                <span class="text-red-700">action #{{ a.failed_action_index }}: {{ a.error_message }}</span>
              {% elif a.payload.get("audit_message") %}
                {{ a.payload.audit_message }}
              {% else %}
                —
              {% endif %}
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 5: Wire the templates dir**

Edit `packages/parcel-shell/src/parcel_shell/ui/templates.py`. Add:

```python
_WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "workflows" / "templates"
```

Inside `get_templates()`, append to the ChoiceLoader's loaders list:

```python
            jinja2.FileSystemLoader(str(_REPORTS_DIR)),
            jinja2.FileSystemLoader(str(_WORKFLOWS_DIR)),
```

- [ ] **Step 6: Verify Jinja resolves them**

```bash
uv run python -c "from parcel_shell.ui.templates import get_templates; t = get_templates(); print([n for n in t.env.loader.list_templates() if n.startswith('workflows/')])"
```

Expected: `['workflows/_action_summary.html', 'workflows/_trigger_summary.html', 'workflows/detail.html', 'workflows/list.html']`

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/templates/ \
        packages/parcel-shell/src/parcel_shell/ui/templates.py
git commit -m "feat(shell): workflow list/detail templates + jinja loader wiring"
```

---

## Task 9: Shell — router (list + detail + manual run)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/router.py`
- Create: `packages/parcel-shell/tests/test_workflows_routes.py`

- [ ] **Step 1: Implement the router**

`packages/parcel-shell/src/parcel_shell/workflows/router.py`:

```python
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_sdk import Manual
from parcel_sdk.shell_api import Flash
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.registry import collect_workflows, find_workflow
from parcel_shell.workflows.runner import dispatch_events

_log = structlog.get_logger("parcel_shell.workflows.router")

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _group_by_module(registered, perms):
    groups: dict[str, list] = {}
    for r in registered:
        if r.workflow.permission in perms:
            groups.setdefault(r.module_name, []).append(r.workflow)
    return sorted(groups.items())


@router.get("", response_class=HTMLResponse)
async def workflows_list(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    groups = _group_by_module(registered, perms)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "workflows/list.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/workflows",
            "settings": request.app.state.settings,
            "permissions": perms,
            "groups": groups,
        },
    )


@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def workflow_detail(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None or hit.workflow.permission not in perms:
        raise _not_found()

    audits = (
        (
            await db.scalars(
                select(WorkflowAudit)
                .where(
                    WorkflowAudit.module == module_name,
                    WorkflowAudit.workflow_slug == slug,
                )
                .order_by(desc(WorkflowAudit.created_at))
                .limit(50)
            )
        )
        .all()
    )

    has_manual = any(isinstance(t, Manual) for t in hit.workflow.triggers)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "workflows/detail.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/workflows",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "workflow": hit.workflow,
            "audits": audits,
            "has_manual_trigger": has_manual,
        },
    )


@router.post("/{module_name}/{slug}/run")
async def workflow_run(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None or hit.workflow.permission not in perms:
        raise _not_found()

    manual_triggers = [t for t in hit.workflow.triggers if isinstance(t, Manual)]
    if not manual_triggers:
        raise _not_found()

    sessionmaker = request.app.state.sessionmaker
    synthetic_event = manual_triggers[0].event
    await dispatch_events(
        [{"event": synthetic_event, "subject": None, "subject_id": None, "changed": ()}],
        sessionmaker,
    )

    response = RedirectResponse(f"/workflows/{module_name}/{slug}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Manually triggered {hit.workflow.title!r}."),
        secret=request.app.state.settings.session_secret,
    )
    return response
```

- [ ] **Step 2: Wire into `create_app`**

Edit `packages/parcel-shell/src/parcel_shell/app.py`. After the reports include:

```python
    from parcel_shell.reports.router import router as reports_router

    app.include_router(reports_router)

    from parcel_shell.workflows.router import router as workflows_router

    app.include_router(workflows_router)
```

Inside the lifespan, after `await sync_active_modules(app)`:

```python
        # Workflows: install the after-commit listener and tell the runner where the app is.
        from parcel_shell.workflows.bus import install_after_commit_listener
        from parcel_shell.workflows.runner import set_active_app

        install_after_commit_listener()
        set_active_app(app)
```

- [ ] **Step 3: Implement `DefaultShellBinding.emit`**

Edit `packages/parcel-shell/src/parcel_shell/shell_api_impl.py`. Append the method to `DefaultShellBinding`:

```python
    async def emit(
        self,
        session: Any,
        event: str,
        subject: Any,
        *,
        changed: tuple[str, ...] = (),
    ) -> None:
        from parcel_shell.workflows.bus import _emit_to_session

        await _emit_to_session(session, event, subject, changed=changed)
```

- [ ] **Step 4: Write the failing route tests**

`packages/parcel-shell/tests/test_workflows_routes.py`:

```python
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

from parcel_sdk import EmitAudit, Manual, Module, OnCreate, Workflow
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module

pytestmark = pytest.mark.asyncio


_WF_OK = Workflow(
    slug="welcome",
    title="Welcome",
    permission="users.read",  # admin already has this
    triggers=(OnCreate("demo.thing.created"),),
    actions=(EmitAudit("hi"),),
)
_WF_GATED = Workflow(
    slug="welcome",
    title="Welcome",
    permission="nobody.has.this",
    triggers=(OnCreate("demo.thing.created"),),
    actions=(EmitAudit("hi"),),
)
_WF_MANUAL = Workflow(
    slug="manual",
    title="Manual run",
    permission="users.read",
    triggers=(Manual("demo.manual"),),
    actions=(EmitAudit("manual run"),),
)


def _mount(app: FastAPI, *workflows: Workflow) -> None:
    m = Module(name="demo", version="0.1.0", workflows=workflows)
    mount_module(
        app,
        DiscoveredModule(
            module=m,
            distribution_name="parcel-mod-demo",
            distribution_version="0.1.0",
        ),
    )


@pytest_asyncio.fixture()
async def authed_with_demo_workflow(app: FastAPI, authed_client: AsyncClient):
    _mount(app, _WF_OK)
    return authed_client


async def test_list_logged_out_redirects(client: AsyncClient, app: FastAPI) -> None:
    _mount(app, _WF_OK)
    r = await client.get("/workflows", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_list_with_visible_workflow(authed_with_demo_workflow: AsyncClient) -> None:
    r = await authed_with_demo_workflow.get("/workflows")
    assert r.status_code == 200
    assert "Welcome" in r.text
    assert "/workflows/demo/welcome" in r.text


async def test_list_hides_workflow_without_permission(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _WF_GATED)
    r = await authed_client.get("/workflows")
    assert r.status_code == 200
    assert "Welcome" not in r.text


async def test_detail_404_on_missing(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/workflows/nope/none")
    assert r.status_code == 404


async def test_detail_404_on_no_permission(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _WF_GATED)
    r = await authed_client.get("/workflows/demo/welcome")
    assert r.status_code == 404


async def test_detail_renders_with_permission(authed_with_demo_workflow: AsyncClient) -> None:
    r = await authed_with_demo_workflow.get("/workflows/demo/welcome")
    assert r.status_code == 200
    assert "Welcome" in r.text
    assert "demo.thing.created" in r.text  # trigger summary
    assert "audit: <code>hi</code>" in r.text  # action summary


async def test_run_404_when_no_manual_trigger(
    authed_with_demo_workflow: AsyncClient,
) -> None:
    r = await authed_with_demo_workflow.post("/workflows/demo/welcome/run")
    assert r.status_code == 404


async def test_run_dispatches_when_manual_trigger(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _WF_MANUAL)
    r = await authed_client.post("/workflows/demo/manual/run", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/workflows/demo/manual"
```

- [ ] **Step 5: Run the route tests**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_routes.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/router.py \
        packages/parcel-shell/src/parcel_shell/app.py \
        packages/parcel-shell/src/parcel_shell/shell_api_impl.py \
        packages/parcel-shell/tests/test_workflows_routes.py
git commit -m "feat(shell): mount /workflows {list, detail, run} + DefaultShellBinding.emit"
```

---

## Task 10: Shell — sidebar `_workflows_section`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`
- Create: `packages/parcel-shell/tests/test_workflows_sidebar.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_workflows_sidebar.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import EmitAudit, Module, OnCreate, Workflow
from parcel_shell.ui.sidebar import _workflows_section


def _wf(slug: str, perm: str) -> Workflow:
    return Workflow(
        slug=slug,
        title=f"Workflow {slug}",
        permission=perm,
        triggers=(OnCreate("x.y.created"),),
        actions=(EmitAudit("hi"),),
    )


def _request(manifest: dict[str, Module]):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    )


def test_section_visible_with_permission() -> None:
    m = Module(name="demo", version="0.1.0", workflows=(_wf("a", "demo.read"),))
    section = _workflows_section(_request({"demo": m}), {"demo.read"})
    assert section is not None
    assert section.label == "Workflows"
    assert section.items[0].href == "/workflows"


def test_section_hidden_without_permission() -> None:
    m = Module(name="demo", version="0.1.0", workflows=(_wf("a", "demo.read"),))
    section = _workflows_section(_request({"demo": m}), set())
    assert section is None


def test_section_hidden_when_no_workflows() -> None:
    m = Module(name="demo", version="0.1.0")
    section = _workflows_section(_request({"demo": m}), {"demo.read"})
    assert section is None
```

- [ ] **Step 2: Implement `_workflows_section` and wire it**

Edit `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`. Add `_workflows_section` after `_reports_section`:

```python
def _workflows_section(request, perms: set[str]) -> SidebarSection | None:
    """Return a sidebar section for /workflows if the user can see >= 1 workflow."""
    manifest = getattr(request.app.state, "active_modules_manifest", {}) or {}
    for module in manifest.values():
        for wf in getattr(module, "workflows", ()):
            if wf.permission in perms:
                return SidebarSection(
                    label="Workflows",
                    items=(SidebarItem(label="Workflows", href="/workflows", permission=None),),
                )
    return None
```

Update `__all__` to include `"_workflows_section"`.

Update `sidebar_for` to insert the workflows section after reports:

```python
def sidebar_for(request, perms: set[str]) -> list[SidebarSection]:
    """Convenience: compose the sidebar using the live app state."""
    module_sections = getattr(request.app.state, "active_modules_sidebar", None)
    out = composed_sections(perms, module_sections)
    insert_at = 1 if out and out[0].label == "Overview" else 0
    dash = _dashboards_section(request, perms)
    if dash is not None:
        out.insert(insert_at, dash)
        insert_at += 1
    rep = _reports_section(request, perms)
    if rep is not None:
        out.insert(insert_at, rep)
        insert_at += 1
    wf = _workflows_section(request, perms)
    if wf is not None:
        out.insert(insert_at, wf)
    return out
```

- [ ] **Step 3: Run sidebar tests**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_sidebar.py packages/parcel-shell/tests/test_reports_sidebar.py packages/parcel-shell/tests/test_ui_layout.py -v
```

Expected: green. (Existing reports + ui_layout tests must continue to pass.)

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/sidebar.py \
        packages/parcel-shell/tests/test_workflows_sidebar.py
git commit -m "feat(shell): inject Workflows sidebar link when user has >= 1 visible workflow"
```

---

## Task 11: Shell — boot-time validation warning

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/modules/integration.py`
- Create: `packages/parcel-shell/tests/test_workflows_boot_validation.py`

- [ ] **Step 1: Write the failing test**

`packages/parcel-shell/tests/test_workflows_boot_validation.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from parcel_sdk import EmitAudit, Module, OnCreate, Permission, Workflow
from parcel_shell.logging import configure_logging
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


def test_mount_warns_when_workflow_permission_not_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()

    bad = Workflow(
        slug="welcome",
        title="Welcome",
        permission="contacts.write",  # NOT in declared permissions
        triggers=(OnCreate("contacts.contact.created"),),
        actions=(EmitAudit("hi"),),
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        workflows=(bad,),
    )
    mount_module(
        app,
        DiscoveredModule(
            module=module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        ),
    )
    out = capsys.readouterr().out
    assert "module.workflow.unknown_permission" in out
    assert "contacts.write" in out


def test_mount_silent_when_workflow_permission_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()
    ok = Workflow(
        slug="welcome",
        title="Welcome",
        permission="contacts.read",
        triggers=(OnCreate("contacts.contact.created"),),
        actions=(EmitAudit("hi"),),
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        workflows=(ok,),
    )
    mount_module(
        app,
        DiscoveredModule(
            module=module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        ),
    )
    out = capsys.readouterr().out
    assert "module.workflow.unknown_permission" not in out
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_boot_validation.py -v
```

Expected: assertion fails — no warning yet.

- [ ] **Step 3: Add the warning to `mount_module`**

Edit `packages/parcel-shell/src/parcel_shell/modules/integration.py`. Inside `mount_module`, after the existing `for report in ...` loop:

```python
    for workflow in getattr(discovered.module, "workflows", ()):
        if workflow.permission not in declared:
            _log.warning(
                "module.workflow.unknown_permission",
                module=name,
                slug=workflow.slug,
                permission=workflow.permission,
            )
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_boot_validation.py packages/parcel-shell/tests/test_reports_boot_validation.py -v
```

Expected: green (4 tests).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/integration.py \
        packages/parcel-shell/tests/test_workflows_boot_validation.py
git commit -m "feat(shell): warn at mount when a workflow's permission isn't declared"
```

---

## Task 12: Contacts — `welcomed_at` migration + model column

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/alembic/versions/0002_add_welcomed_at.py`
- Modify: `modules/contacts/src/parcel_mod_contacts/models.py`

- [ ] **Step 1: Inspect contacts migration 0001**

```bash
ls modules/contacts/src/parcel_mod_contacts/alembic/versions/
cat modules/contacts/src/parcel_mod_contacts/alembic/versions/0001_*.py | head -30
```

Note the revision id format and import style.

- [ ] **Step 2: Write the migration**

`modules/contacts/src/parcel_mod_contacts/alembic/versions/0002_add_welcomed_at.py`:

```python
"""add welcomed_at to contacts

Revision ID: 0002_add_welcomed_at
Revises: 0001_create_contacts_schema   <-- replace with the actual 0001 revision id
Create Date: 2026-04-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_add_welcomed_at"
down_revision = "0001_create_contacts_schema"  # replace with the actual revision id
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("welcomed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        schema="mod_contacts",
    )


def downgrade() -> None:
    op.drop_column("contacts", "welcomed_at", schema="mod_contacts")
```

(Open the existing 0001 migration to copy the exact `revision = "..."` string into `down_revision`.)

- [ ] **Step 3: Add the column to the model**

Edit `modules/contacts/src/parcel_mod_contacts/models.py`. In `class Contact`, after `updated_at`:

```python
    welcomed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
```

- [ ] **Step 4: Run the existing contacts migration tests to confirm head moves cleanly**

```bash
uv run pytest modules/contacts/tests/test_contacts_migrations.py -v
```

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/alembic/versions/0002_add_welcomed_at.py \
        modules/contacts/src/parcel_mod_contacts/models.py
git commit -m "feat(contacts): add welcomed_at column (migration 0002)"
```

---

## Task 13: Contacts — welcome workflow + `emit()` in router

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/workflows.py`
- Modify: `modules/contacts/src/parcel_mod_contacts/__init__.py`
- Modify: `modules/contacts/src/parcel_mod_contacts/router.py`
- Modify: `modules/contacts/pyproject.toml`
- Create: `modules/contacts/tests/test_contacts_workflow_welcome.py`

- [ ] **Step 1: Write the workflow**

`modules/contacts/src/parcel_mod_contacts/workflows.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

from parcel_sdk import EmitAudit, OnCreate, UpdateField, Workflow, WorkflowContext


def _now(_ctx: WorkflowContext) -> datetime:
    return datetime.now(UTC)


welcome_workflow = Workflow(
    slug="new_contact_welcome",
    title="Welcome new contact",
    permission="contacts.read",
    triggers=(OnCreate("contacts.contact.created"),),
    actions=(
        UpdateField(field="welcomed_at", value=_now),
        EmitAudit(message="Welcomed {{ subject.first_name or subject.email }}"),
    ),
    description="Stamps welcomed_at and writes a friendly audit message when a contact is created.",
)
```

- [ ] **Step 2: Wire into the manifest**

Edit `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
from __future__ import annotations

from pathlib import Path

from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_mod_contacts.models import metadata
from parcel_mod_contacts.reports import directory_report
from parcel_mod_contacts.router import router
from parcel_mod_contacts.sidebar import SIDEBAR_ITEMS
from parcel_mod_contacts.workflows import welcome_workflow
from parcel_sdk import Module, Permission

module = Module(
    name="contacts",
    version="0.4.0",
    permissions=(
        Permission("contacts.read", "View contacts and companies"),
        Permission("contacts.write", "Create, update, and delete contacts and companies"),
    ),
    capabilities=(),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=SIDEBAR_ITEMS,
    dashboards=(overview_dashboard,),
    reports=(directory_report,),
    workflows=(welcome_workflow,),
)

__all__ = ["module"]
```

- [ ] **Step 3: Bump pyproject version**

Edit `modules/contacts/pyproject.toml`: `version = "0.3.0"` → `version = "0.4.0"`.

- [ ] **Step 4: Add `emit()` to the contacts POST handler**

Find the create-contact handler in `modules/contacts/src/parcel_mod_contacts/router.py`:

```bash
grep -n "POST\|router.post\|contacts.contact.created\|db.commit" modules/contacts/src/parcel_mod_contacts/router.py
```

Locate the POST that creates a contact. After the `await db.commit()` (or equivalent — look for the SQLAlchemy session commit on a successful create), add:

```python
    from parcel_sdk import shell_api

    await shell_api.emit(db, "contacts.contact.created", new_contact)
```

(Use whatever variable name the handler already uses for the new contact — `new_contact`, `contact`, `c`, etc. The import can also be moved to the top of the file if preferred.)

- [ ] **Step 5: Write the integration test**

`modules/contacts/tests/test_contacts_workflow_welcome.py`:

```python
from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_mod_contacts.models import Contact
from parcel_shell.workflows.models import WorkflowAudit

pytestmark = pytest.mark.asyncio


async def test_creating_a_contact_triggers_welcome_workflow(
    authed_contacts: AsyncClient, settings
) -> None:
    """POSTing a contact should fire the workflow, populate welcomed_at,
    and write an 'ok' audit row."""
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "ada@example.com", "first_name": "Ada", "last_name": "Lovelace"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # The dispatch is fire-and-forget via asyncio.create_task; give it a tick
    # to settle. Polling with a short loop is robust without flakiness.
    eng = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)

    welcomed: bool = False
    audit_count: int = 0
    try:
        for _ in range(40):  # up to ~2s
            await asyncio.sleep(0.05)
            async with factory() as s:
                contact = (
                    await s.scalars(select(Contact).where(Contact.email == "ada@example.com"))
                ).one()
                if contact.welcomed_at is not None:
                    welcomed = True
                rows = (
                    await s.scalars(
                        select(WorkflowAudit).where(
                            WorkflowAudit.workflow_slug == "new_contact_welcome"
                        )
                    )
                ).all()
                audit_count = len(rows)
            if welcomed and audit_count >= 1:
                break
    finally:
        await eng.dispose()

    assert welcomed, "Contact.welcomed_at was never set"
    assert audit_count == 1
    async with factory() as s:
        row = (
            await s.scalars(
                select(WorkflowAudit).where(
                    WorkflowAudit.workflow_slug == "new_contact_welcome"
                )
            )
        ).one()
        assert row.status == "ok"
        assert row.event == "contacts.contact.created"
        assert row.subject_id is not None
        assert "Welcomed Ada" in row.payload.get("audit_message", "")
    await eng.dispose()


async def test_manual_run_route_returns_404_for_oncreate_only_workflow(
    authed_contacts: AsyncClient,
) -> None:
    r = await authed_contacts.post(
        "/workflows/contacts/new_contact_welcome/run", follow_redirects=False
    )
    assert r.status_code == 404
```

- [ ] **Step 6: Run the integration tests**

```bash
uv run pytest modules/contacts/tests/test_contacts_workflow_welcome.py -v
```

Expected: 2 passed. (The first test polls for up to ~2s for the post-commit dispatch to settle; the welcome timestamp + audit row should both appear well within that window.)

- [ ] **Step 7: Run the full contacts test suite**

```bash
uv run pytest modules/contacts/tests/ -v
```

Expected: all green. Existing contacts tests should not regress.

- [ ] **Step 8: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/__init__.py \
        modules/contacts/src/parcel_mod_contacts/workflows.py \
        modules/contacts/src/parcel_mod_contacts/router.py \
        modules/contacts/pyproject.toml \
        modules/contacts/tests/test_contacts_workflow_welcome.py
git commit -m "feat(contacts): ship welcome workflow + emit + bump to 0.4.0"
```

---

## Task 14: Documentation

**Files:**
- Modify: `docs/module-authoring.md`
- Modify: `CLAUDE.md`
- Modify: `docs/index.html`

- [ ] **Step 1: Add a "Workflows" section to `module-authoring.md`**

Append to the end of the file:

````markdown


## Workflows (Phase 10a)

A module can declare any number of **workflows** — trigger→action chains that
run automatically when the shell observes events emitted from that module's
endpoints. Phase 10a covers synchronous triggers and two minimal actions
(`UpdateField`, `EmitAudit`); cron / queued / rich actions arrive in 10b/10c.

### Declaring a workflow

```python
# src/parcel_mod_<name>/workflows.py
from datetime import UTC, datetime

from parcel_sdk import EmitAudit, OnCreate, UpdateField, Workflow, WorkflowContext


def _now(_ctx: WorkflowContext) -> datetime:
    return datetime.now(UTC)


welcome = Workflow(
    slug="new_contact_welcome",
    title="Welcome new contact",
    permission="contacts.read",
    triggers=(OnCreate("contacts.contact.created"),),
    actions=(
        UpdateField(field="welcomed_at", value=_now),
        EmitAudit(message="Welcomed {{ subject.first_name or subject.email }}"),
    ),
)
```

Wire it into the manifest:

```python
module = Module(
    name="contacts",
    version="0.4.0",
    ...,
    workflows=(welcome,),
)
```

### Triggers

| Trigger | Fires when |
|---|---|
| `OnCreate(event)` | The named event is emitted via `shell_api.emit`. |
| `OnUpdate(event, when_changed=())` | Same, with optional filter — `when_changed=("email",)` fires only when "email" is in the emitted `changed` list. Empty tuple matches any update event with the right name. |
| `Manual(event)` | Never fires from `emit`. Only via `POST /workflows/<module>/<slug>/run`, which dispatches a synthetic event with the trigger's `event` name. |

### Actions

| Action | Behaviour |
|---|---|
| `UpdateField(field, value)` | Re-fetches the trigger's subject by id in the workflow's session, sets `field` to `value` (literal or `Callable[[WorkflowContext], Any]`), commits the new session. |
| `EmitAudit(message)` | Renders the Jinja template against `{subject, event, ctx}` and stores the result in the audit row's `payload.audit_message`. No side effect beyond the audit row — purely for human readability. |

### Wiring `emit`

Module endpoints emit events explicitly, after the relevant DB write:

```python
@router.post("/")
async def create_contact(
    request: Request,
    user=Depends(shell_api.require_permission("contacts.write")),
    db: AsyncSession = Depends(shell_api.get_session()),
):
    new_contact = Contact(...)
    db.add(new_contact)
    await db.commit()
    await shell_api.emit(db, "contacts.contact.created", new_contact)
    return RedirectResponse("/mod/contacts/", status_code=303)
```

The signature is `emit(session, event, subject, *, changed=())`. Subject is
typically a SQLAlchemy model whose `.id` is read for `subject_id`. The shell
queues the event on `session.info` and dispatches workflows after the request
session commits — your handler returns immediately; workflows run on a fresh
session in the background.

### Failure semantics

A workflow's actions run in a single transaction in the dispatch session. If
any action raises, the entire chain rolls back and the audit row is written
with `status="error"` and `failed_action_index` pointing at the failing
action. The originating handler's commit (which already succeeded) is
untouched.

### Permissions and the audit log

`Workflow.permission` is one of your module's own permissions (e.g.
`contacts.read`). It gates both the audit log view at
`/workflows/<module>/<slug>` and the manual-run POST endpoint. There are no
shell-level `workflows.*` permissions and no shell migrations beyond the
audit table itself.

If `Workflow.permission` doesn't match any permission your module declares,
the shell logs `module.workflow.unknown_permission` at WARN on mount. The
workflow still mounts but no user can ever see it.

### Testing workflows

Unit-test action data flow against a real session:

```python
async def test_update_field_sets_welcomed_at(contacts_session):
    c = Contact(...)
    contacts_session.add(c)
    await contacts_session.commit()
    ctx = WorkflowContext(session=contacts_session, ...)
    await execute_action(UpdateField("welcomed_at", _now), ctx, payload={})
    assert c.welcomed_at is not None
```

End-to-end through the live app: POST a contact, then poll for the
`welcomed_at` column + an audit row with `status='ok'`. See
`modules/contacts/tests/test_contacts_workflow_welcome.py` for the reference.

### What's not in 10a

- **`OnSchedule(cron)`** — lands in 10b alongside ARQ.
- **`send_email`, `call_webhook`, `run_module_function`, `generate_report`** actions — 10c.
- **State machines** — workflows are chains. Use a state column + `OnUpdate` triggers if you need state-machine-like behaviour today; richer support comes later.
- **Retry** — if an action raises, no retry. The audit row records the failure; admin can re-trigger via the manual route if the workflow declares `Manual`.
````

- [ ] **Step 2: Update `CLAUDE.md`**

In the "Phased roadmap" table, change Phase 10:

```markdown
| 10 | ✅ done (10a) | Workflows — engine + sync triggers + UpdateField/EmitAudit + read-only UI (10a). 10b = cron + ARQ + worker. 10c = rich actions. |
| 11 |  | Sandbox preview enrichment — sample-record seeding, Playwright screenshots, builds on ARQ |
```

Replace the "Current phase" paragraph wholesale:

```markdown
## Current phase

**Phase 10a — Workflows (engine + sync triggers) done.** Modules can now declare `Workflow(...)` chains on their manifest; the shell observes `shell_api.emit(session, event, subject)` calls from module endpoints and dispatches matching workflows post-commit, in a fresh session, with one transaction per chain. Three trigger types: `OnCreate(event)`, `OnUpdate(event, when_changed=())`, `Manual(event)`. Two action types: `UpdateField(field, value)` (literal or callable), `EmitAudit(message)` (Jinja-rendered). Failure semantics: any action raises → chain rolls back, audit row written in a separate session with `status='error'` + `failed_action_index`. Source-write (already committed) is unaffected; no retry until 10b's ARQ infra. New shell migration 0007 adds `shell.workflow_audit`. Per-workflow permission gating (`Workflow.permission` is the module's own permission); 404 (not 403) on missing. Read-only admin UI at `/workflows` (list grouped by module + per-workflow detail with last-50 audit + manual-run POST when a `Manual` trigger is declared). Sidebar auto-injects a single "Workflows" link when the user has ≥ 1 visible workflow. SDK bumped to `0.6.0` (adds `Workflow`, `OnCreate`, `OnUpdate`, `Manual`, `UpdateField`, `EmitAudit`, `WorkflowContext`, `shell_api.emit`); Contacts bumped to `0.4.0` and ships a reference `new_contact_welcome` workflow + a `welcomed_at` column (contacts migration 0002). Boot-time WARN (`module.workflow.unknown_permission`) when a declared workflow points at a permission the module doesn't own. Test count climbs from 347 → ~382.

Next: **Phase 10b — Workflows scheduled triggers + ARQ + worker container** (`OnSchedule(cron)` triggers, ARQ becomes first-class infra, the shell image gains an `entrypoint worker` subcommand, retry semantics arrive on top of the queue). Phase 10c follows with the remaining action library (`send_email` / `call_webhook` / `run_module_function` / `generate_report`) + richer audit UI. Start a new session; prompt: "Begin Phase 10b per `CLAUDE.md` roadmap." The full upcoming roadmap (10a Workflows-engine ✅ → 10b Cron+ARQ → 10c Rich actions → 11 Sandbox preview enrichment) is described below under "Upcoming phases".
```

Add a new block to "Locked-in decisions" (insert after the Report rows from Phase 9):

```markdown
| Workflow declaration | `Module.workflows: tuple[Workflow, ...] = ()`. `Workflow` is a frozen `kw_only=True` SDK dataclass (`slug`, `title`, `permission`, `triggers`, `actions`, optional `description`). Triggers are frozen dataclasses (`OnCreate`, `OnUpdate(when_changed=())`, `Manual`); actions are frozen dataclasses (`UpdateField`, `EmitAudit`). `WorkflowContext(session, event, subject, subject_id, changed)` is passed to action callables. |
| Workflow event bus | Explicit `shell_api.emit(session, event, subject, *, changed=())` from module endpoints — not SQLAlchemy event listeners. Modules opt their writes into observation; explicit emit is greppable, testable, and avoids accidental fires from migrations / fixtures / bulk inserts. |
| Workflow timing | Post-commit. `emit` queues events on `session.info["pending_events"]`; SQLAlchemy `after_commit` listener (registered once at shell startup) drains the queue and `asyncio.create_task`s `runner.dispatch_events(events, sessionmaker)`. Dispatch opens a fresh session per chain — source write always succeeds independently. |
| Workflow failure | Single transaction per chain invocation. Any action raises → chain rolls back, audit row written in a separate session with `status='error'`, `failed_action_index`, and `error_message`. Source write (already committed) is unaffected. No retry in 10a. |
| Workflow audit | New shell table `shell.workflow_audit` (migration 0007). Columns: id, created_at, module, workflow_slug, event, subject_id, status (`ok`/`error`), error_message, failed_action_index, payload jsonb. Index on `(module, workflow_slug, created_at desc)` for the detail-page query. |
| Workflow URLs | Three: `GET /workflows` (list, grouped by module, filtered by permission), `GET /workflows/<module>/<slug>` (declaration summary + last-50 audit), `POST /workflows/<module>/<slug>/run` (manual trigger; only valid when workflow declares a `Manual` trigger). All three return 404 (never 403) on missing permission. |
| Workflow sidebar | Single aggregate "Workflows" link injected by `_workflows_section` when the user has permission for ≥ 1 declared workflow. Inserted after the Reports section. Mirrors `_dashboards_section`'s aggregate-link pattern. |
| Workflow permission model | Per-workflow only. `Workflow.permission` references a permission the module already owns. No shell-level `workflows.*` permissions. `mount_module` emits `module.workflow.unknown_permission` at WARN if the declared permission isn't in the module's `permissions` tuple. |
```

Update the "Phase 10 — Workflows" scope section ("Upcoming phases — scope and open questions") to mark 10a shipped and rename future ones:

```markdown
### Phase 10a — Workflows (engine + sync triggers) ✅ shipped

Shipped on the `phase-10a-workflows` branch. See the "Workflow *" rows under "Locked-in decisions" for the concrete contracts. Engine landed as trigger→action chains (no state machines); sync triggers only (`OnCreate`, `OnUpdate`, `Manual`); two minimal actions (`UpdateField`, `EmitAudit`); explicit `shell_api.emit(session, event, subject)` at endpoints; post-commit dispatch via SQLAlchemy `after_commit`; single-transaction-per-chain failure with audit-on-error; per-workflow permission gating; read-only admin UI at `/workflows`. Contacts ships `new_contact_welcome` as the reference.

### Phase 10b — Workflows (scheduled triggers + ARQ)

**Scope.** Add `OnSchedule(cron)` triggers. ARQ arrives as first-class infrastructure: the shell image gets an `entrypoint worker` subcommand, docker-compose gets a `worker` service, the runner's `dispatch_events` learns to enqueue async jobs instead of `asyncio.create_task`. Retry semantics ride on top of the queue (per-workflow `max_retries`, exponential backoff). The runner stays the same shape; the queue is a layer below.

### Phase 10c — Workflows (rich actions + UI)

**Scope.** Add `send_email`, `call_webhook`, `run_module_function`, `generate_report` actions (the last hooks into Phase 9). Each action declaration carries a capability and re-uses the Phase 7a gate when an AI-generated module declares a workflow. Long-running actions always go through ARQ, never inline. Admin UI gains a richer audit page (filter by status / event / module, retry-failed-invocation button) and a "running instances" view if state-machine semantics land in this phase.
```

- [ ] **Step 3: Update the website**

Edit `docs/index.html`. Update the hero stat-line:

```html
    <div class="stat-line"><span class="dot"></span> Phases 1–9 + 10a complete: shell, auth + RBAC, modules, admin UI, Contacts, SDK + CLI, gate + sandbox, Claude generator + chat, dashboards, reports (Pydantic forms + headless-Chromium PDF), and workflows (sync triggers + minimal actions + read-only audit UI). Phase 10b (scheduled triggers + ARQ) up next; rich actions and sandbox preview enrichment follow.</div>
```

Update the roadmap rows:

```html
      <li>
        <span class="phase-num">9</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">Reports + PDF generation — Pydantic-driven parameter forms, HTML preview, headless-Chromium PDF (Playwright)</span>
      </li>
      <li>
        <span class="phase-num">10a</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">Workflows engine — trigger→action chains, sync triggers (OnCreate/OnUpdate/Manual), UpdateField + EmitAudit, read-only UI</span>
      </li>
      <li>
        <span class="phase-num">10b</span>
        <span class="phase-status next">⏭ next</span>
        <span class="phase-goal">Workflows: scheduled triggers + ARQ — OnSchedule(cron), worker container, retry on top of the queue</span>
      </li>
      <li>
        <span class="phase-num">10c</span>
        <span class="phase-status pending">planned</span>
        <span class="phase-goal">Workflows: rich actions — send_email, call_webhook, run_module_function, generate_report; richer audit UI</span>
      </li>
      <li>
        <span class="phase-num">11</span>
        <span class="phase-status pending">planned</span>
        <span class="phase-goal">Sandbox preview enrichment — sample records, Playwright screenshots, builds on ARQ</span>
      </li>
```

(The original had a single `phase-num="10"` row; replace with the three rows above. Adjust `phase-num="9"` only if pytest count changed.)

Update the test count in the quickstart:

```html
<pre><code>uv run pytest                              <span style="color: var(--fg-muted)"># 382 tests, ~140s</span></code></pre>
```

- [ ] **Step 4: Run the full test suite once before final commit**

```bash
uv run pyright
uv run ruff check
uv run ruff format
uv run pytest -q
```

Expected: green. Test count ~382.

- [ ] **Step 5: Commit**

```bash
git add docs/module-authoring.md CLAUDE.md docs/index.html
git commit -m "docs: phase 10a workflows authoring guide + CLAUDE.md + website update"
```

---

## Task 15: Final verification

- [ ] **Step 1: Boot the dev server and click through manually**

```bash
docker compose up -d
uv run parcel migrate
uv run parcel dev
```

In a browser:

1. Log in as admin.
2. Confirm sidebar shows a "Workflows" link (parallel to "Dashboards", "Reports").
3. Click `/workflows` — see the Contacts welcome workflow listed.
4. Click into `/workflows/contacts/new_contact_welcome` — see triggers + actions + empty audit table.
5. Create a new contact via `/mod/contacts/`.
6. Refresh the workflow detail page — see one audit row with `status="ok"`, the rendered welcome message, and verify the contact's detail page shows a non-null `welcomed_at`.
7. Manually visit `/workflows/contacts/new_contact_welcome/run` (POST) — should 404 (no `Manual` trigger declared).

If anything looks off, patch inline.

- [ ] **Step 2: Stop the dev server**

```bash
docker compose down
```

- [ ] **Step 3: Run the full test suite one more time**

```bash
uv run pytest -q
```

Expected: ~382 passed.

- [ ] **Step 4: Push the branch and open a PR**

```bash
git push -u origin phase-10a-workflows
gh pr create --base main --title "Phase 10a: Workflows (engine + sync triggers)" --body "..."
```

(Use a body modeled on PR #16, with summary, what-shipped, deviations, test plan.)

---

## Self-review checklist (run before handoff)

- [x] **Spec coverage:** every locked decision has a task — phase split (Task 1's spec/plan deviation note), workflow shape (Task 1), trigger types (Task 1, Task 7's `_matches`), action types (Task 1, Task 7's `execute_action`), wiring (Task 5 bus, Task 13 contacts emit), timing (Task 5 after_commit), failure (Task 7 single-txn-per-chain + audit-on-error), audit table (Task 4), permission model (Task 9 router 404, Task 11 boot warning), UI surface (Task 9 list/detail/run), sidebar (Task 10), reference workflow (Tasks 12-13), SDK 0.6.0 (Task 1), Contacts 0.4.0 (Task 13).
- [x] **Placeholder scan:** no "TBD" / "implement later" / "similar to Task N" — every code step shows actual code.
- [x] **Type consistency:** `Workflow(slug, title, permission, triggers, actions, description)` matches across SDK, registry, runner, router, templates. `WorkflowContext(session, event, subject, subject_id, changed)` matches across SDK and runner. `emit(session, event, subject, *, changed=())` matches across SDK Protocol, public accessor, `_emit_to_session`, and the contacts integration.
- [x] **Spec deviations:** flagged at the top — `emit(session, ...)` instead of contextvar resolution, listener install location, sessionmaker stash on `session.info`.

---

**Plan complete. Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.
