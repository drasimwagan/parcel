# Phase 10b-retry — Per-workflow retry semantics implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in retry semantics to workflows. `Workflow.max_retries` (default 0) + `Workflow.retry_backoff_seconds` (default 30, exponential) thread through `run_workflow` (refactored to return `WorkflowOutcome`) and worker handlers (which raise `arq.Retry` when retries remain). New `attempt: int` column on `shell.workflow_audit` (migration 0008) records each try.

**Architecture:** SDK `Workflow` gains two fields with construction-time validation. `WorkflowAudit.attempt` is added via additive migration with `server_default=1` so existing rows backfill cleanly. `run_workflow` is refactored to return a `WorkflowOutcome(status, error_message, failed_action_index)` dataclass — the caller (worker handler or inline dispatcher) reads it. Worker handlers `run_event_dispatch` and `run_scheduled_workflow` consult `ctx["job_try"]` (ARQ-provided), pass it as `attempt` to `run_workflow`, and raise `arq.Retry(defer=...)` when the outcome is error and the retry budget remains. Inline mode (`PARCEL_WORKFLOWS_INLINE=1`) calls `dispatch_events` which always passes `attempt=1` — no retry path.

**Tech Stack:** Python 3.12, ARQ 0.28+, SQLAlchemy 2.0 async, Alembic, pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-04-25-phase-10b-retry-design.md`](../specs/2026-04-25-phase-10b-retry-design.md)

**Spec deviations:** None. The mechanical decisions in the spec map cleanly to code.

---

## File structure

### Created

| Path | Responsibility |
|---|---|
| `packages/parcel-shell/src/parcel_shell/alembic/versions/0008_workflow_audit_attempt.py` | Migration adding `attempt` column |
| `packages/parcel-shell/tests/test_migrations_0008.py` | Migration smoke test |

### Modified

| Path | Change |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/workflows.py` | Add `max_retries` + `retry_backoff_seconds` fields with `__post_init__` validation |
| `packages/parcel-sdk/src/parcel_sdk/__init__.py` | Bump `__version__` to `0.8.0` |
| `packages/parcel-sdk/tests/test_workflows.py` | Tests for new fields + validation |
| `packages/parcel-shell/src/parcel_shell/workflows/models.py` | `WorkflowAudit` gains `attempt` column |
| `packages/parcel-shell/src/parcel_shell/workflows/runner.py` | `WorkflowOutcome` dataclass; `run_workflow` returns it + accepts `attempt` kwarg |
| `packages/parcel-shell/src/parcel_shell/workflows/worker.py` | `run_event_dispatch` + `run_scheduled_workflow` consult `ctx["job_try"]` and raise `arq.Retry` |
| `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/detail.html` | Add `Attempt` column |
| `packages/parcel-shell/tests/test_workflows_runner.py` | Tests for `attempt` kwarg + `WorkflowOutcome` return |
| `packages/parcel-shell/tests/test_workflows_worker.py` | Tests for retry decision logic |
| `packages/parcel-shell/tests/test_workflows_worker_integration.py` | E2E retry test through real ARQ |
| `docs/module-authoring.md` | New "Retries" subsection |
| `CLAUDE.md` | Phase 10b-retry → done; locked-decisions block; current-phase + next-phase pointer |
| `docs/index.html` | Roadmap row for 10b-retry done; 10c next |

---

## Task 1: SDK — `Workflow.max_retries` + `Workflow.retry_backoff_seconds`

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/workflows.py`
- Modify: `packages/parcel-sdk/tests/test_workflows.py`

- [ ] **Step 1: Append failing tests to `test_workflows.py`**

```python
def test_workflow_max_retries_defaults_zero() -> None:
    w = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    assert w.max_retries == 0


def test_workflow_retry_backoff_seconds_defaults_30() -> None:
    w = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    assert w.retry_backoff_seconds == 30


def test_workflow_accepts_max_retries_and_backoff() -> None:
    w = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
        max_retries=3,
        retry_backoff_seconds=10,
    )
    assert w.max_retries == 3
    assert w.retry_backoff_seconds == 10


def test_workflow_rejects_negative_max_retries() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        Workflow(
            slug="t",
            title="T",
            permission="x.read",
            triggers=(OnCreate("a"),),
            actions=(EmitAudit("hi"),),
            max_retries=-1,
        )


def test_workflow_rejects_zero_retry_backoff_seconds() -> None:
    with pytest.raises(ValueError, match="retry_backoff_seconds"):
        Workflow(
            slug="t",
            title="T",
            permission="x.read",
            triggers=(OnCreate("a"),),
            actions=(EmitAudit("hi"),),
            retry_backoff_seconds=0,
        )
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v -k "max_retries or retry_backoff"
```

Expected: 5 failures — fields don't exist yet.

- [ ] **Step 3: Add fields + validation to `workflows.py`**

In `packages/parcel-sdk/src/parcel_sdk/workflows.py`, edit the `Workflow` dataclass:

```python
@dataclass(frozen=True, kw_only=True)
class Workflow:
    """A trigger-to-action chain attached to a module manifest."""

    slug: str
    title: str
    permission: str
    triggers: tuple[Trigger, ...]
    actions: tuple[Action, ...]
    description: str = ""
    max_retries: int = 0
    retry_backoff_seconds: int = 30

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(
                f"Workflow max_retries={self.max_retries} must be >= 0"
            )
        if self.retry_backoff_seconds < 1:
            raise ValueError(
                f"Workflow retry_backoff_seconds={self.retry_backoff_seconds} must be >= 1"
            )
```

- [ ] **Step 4: Bump SDK version**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py`:

```python
__version__ = "0.8.0"
```

Update the docstring to "Phase 10b-retry surface: Phase 10b + per-workflow retry semantics."

- [ ] **Step 5: Run and verify pass**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v
```

Expected: 24 passed (19 from prior phases + 5 new).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/workflows.py \
        packages/parcel-sdk/src/parcel_sdk/__init__.py \
        packages/parcel-sdk/tests/test_workflows.py
git commit -m "feat(sdk): add Workflow.max_retries + retry_backoff_seconds"
```

---

## Task 2: Migration 0008 — `workflow_audit.attempt`

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0008_workflow_audit_attempt.py`
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/models.py`
- Create: `packages/parcel-shell/tests/test_migrations_0008.py`

- [ ] **Step 1: Write the migration**

`packages/parcel-shell/src/parcel_shell/alembic/versions/0008_workflow_audit_attempt.py`:

```python
"""workflow_audit.attempt

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-25 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_audit",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        schema="shell",
    )


def downgrade() -> None:
    op.drop_column("workflow_audit", "attempt", schema="shell")
```

- [ ] **Step 2: Add `attempt` to the model**

Edit `packages/parcel-shell/src/parcel_shell/workflows/models.py`. After `payload`:

```python
    attempt: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
```

Add `text` to the import from `sqlalchemy`:

```python
from sqlalchemy import JSON, Integer, Text, func, text
```

- [ ] **Step 3: Write the migration test**

`packages/parcel-shell/tests/test_migrations_0008.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "src" / "parcel_shell" / "alembic.ini"


def _cfg(url: str) -> Config:
    c = Config(str(ALEMBIC_INI))
    c.set_main_option("sqlalchemy.url", url)
    return c


async def test_0008_adds_attempt_column(database_url: str, engine: AsyncEngine) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name, column_default, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'shell' "
                    "AND table_name = 'workflow_audit' "
                    "AND column_name = 'attempt'"
                )
            )
        ).all()
    assert len(rows) == 1
    assert rows[0][2] == "NO"  # NOT NULL


async def test_0008_existing_rows_get_attempt_default(
    database_url: str, engine: AsyncEngine
) -> None:
    """Insert a row before applying 0008, upgrade, confirm attempt=1."""
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "0007")
    import uuid

    rid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO shell.workflow_audit "
                "(id, module, workflow_slug, event, status, payload) "
                "VALUES (:id, 'm', 's', 'e', 'ok', '{}'::json)"
            ),
            {"id": rid},
        )
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    async with engine.connect() as conn:
        attempt = (
            await conn.execute(
                text("SELECT attempt FROM shell.workflow_audit WHERE id = :id"),
                {"id": rid},
            )
        ).scalar_one()
    assert attempt == 1
    # Cleanup so the test is idempotent across runs.
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM shell.workflow_audit WHERE id = :id"), {"id": rid}
        )


async def test_0008_downgrade_drops_column(
    database_url: str, engine: AsyncEngine
) -> None:
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
    await asyncio.to_thread(command.downgrade, _cfg(database_url), "0007")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'shell' "
                    "AND table_name = 'workflow_audit' "
                    "AND column_name = 'attempt'"
                )
            )
        ).all()
    assert rows == []
    # Restore for sibling tests.
    await asyncio.to_thread(command.upgrade, _cfg(database_url), "head")
```

- [ ] **Step 4: Run the migration tests**

```bash
uv run pytest packages/parcel-shell/tests/test_migrations_0008.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/alembic/versions/0008_workflow_audit_attempt.py \
        packages/parcel-shell/src/parcel_shell/workflows/models.py \
        packages/parcel-shell/tests/test_migrations_0008.py
git commit -m "feat(shell): migration 0008 adds attempt column to workflow_audit"
```

---

## Task 3: Runner — `WorkflowOutcome` + `run_workflow(attempt=)`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/runner.py`
- Modify: `packages/parcel-shell/tests/test_workflows_runner.py`

- [ ] **Step 1: Append failing tests to `test_workflows_runner.py`**

```python
async def test_run_workflow_returns_workflow_outcome_on_success(
    sessionmaker_factory,
) -> None:
    from parcel_shell.workflows.runner import WorkflowOutcome

    wf = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    ev = {"event": "a", "subject": None, "subject_id": None, "changed": ()}
    outcome = await run_workflow("demo", wf, ev, sessionmaker_factory)
    assert isinstance(outcome, WorkflowOutcome)
    assert outcome.status == "ok"
    assert outcome.error_message is None
    assert outcome.failed_action_index is None


async def test_run_workflow_returns_workflow_outcome_on_error(
    sessionmaker_factory,
) -> None:
    from parcel_shell.workflows.runner import WorkflowOutcome

    wf = Workflow(
        slug="bad",
        title="B",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(
            EmitAudit("first"),
            UpdateField(field="x", value=1),  # subject is None -> RuntimeError
        ),
    )
    ev = {"event": "a", "subject": None, "subject_id": None, "changed": ()}
    outcome = await run_workflow("demo", wf, ev, sessionmaker_factory)
    assert isinstance(outcome, WorkflowOutcome)
    assert outcome.status == "error"
    assert outcome.failed_action_index == 1
    assert outcome.error_message is not None and "subject_id" in outcome.error_message


async def test_run_workflow_writes_attempt_to_audit(sessionmaker_factory) -> None:
    """Calling with attempt=2 stores 2 in the audit row."""
    from sqlalchemy import select

    wf = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    ev = {"event": "a", "subject": None, "subject_id": None, "changed": ()}
    await run_workflow("demo", wf, ev, sessionmaker_factory, attempt=2)

    async with sessionmaker_factory() as s:
        row = (await s.scalars(select(WorkflowAudit))).one()
        assert row.attempt == 2


async def test_run_workflow_attempt_defaults_to_1(sessionmaker_factory) -> None:
    from sqlalchemy import select

    wf = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    ev = {"event": "a", "subject": None, "subject_id": None, "changed": ()}
    await run_workflow("demo", wf, ev, sessionmaker_factory)

    async with sessionmaker_factory() as s:
        row = (await s.scalars(select(WorkflowAudit))).one()
        assert row.attempt == 1
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_runner.py -v -k "attempt or workflow_outcome"
```

Expected: ImportError on `WorkflowOutcome` + AttributeError on `attempt` kwarg.

- [ ] **Step 3: Refactor `run_workflow`**

Edit `packages/parcel-shell/src/parcel_shell/workflows/runner.py`. Add the dataclass at the top of the file (after the `_active_app` declaration):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowOutcome:
    """Result of a single `run_workflow` invocation, returned to callers
    (worker handlers) so they can decide whether to retry."""

    status: str  # "ok" | "error"
    error_message: str | None
    failed_action_index: int | None
```

Refactor `run_workflow`'s signature and return:

```python
async def run_workflow(
    module_name: str,
    workflow: Workflow,
    ev: dict,
    sessionmaker: async_sessionmaker,
    *,
    attempt: int = 1,
) -> WorkflowOutcome:
    """Execute one workflow's chain in a single transaction; audit the outcome.

    Returns the outcome so callers (worker handlers) can decide whether to
    retry. The audit row is written internally in a separate session and
    survives any chain rollback.
    """
    payload: dict[str, Any] = {}
    failed_idx: int | None = None
    error_message: str | None = None
    status = "ok"
    idx = -1

    async with sessionmaker() as session:
        ctx = WorkflowContext(
            session=session,
            event=ev["event"],
            subject=ev["subject"],
            subject_id=ev["subject_id"],
            changed=ev.get("changed", ()),
        )
        try:
            for idx, action in enumerate(workflow.actions):  # noqa: B007
                await execute_action(action, ctx, payload)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            failed_idx = idx if idx >= 0 else 0
            error_message = str(exc)
            status = "error"
            _log.warning(
                "workflows.action_failed",
                module=module_name,
                slug=workflow.slug,
                action_index=failed_idx,
                error=error_message,
            )

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
                attempt=attempt,
            )
        )
        await audit_session.commit()

    return WorkflowOutcome(
        status=status,
        error_message=error_message,
        failed_action_index=failed_idx,
    )
```

`dispatch_events` calls `run_workflow` without the `attempt` kwarg — defaults to 1. No retry path on the inline side; the existing behaviour is preserved.

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_runner.py -v
```

Expected: 14 passed (10 from 10b + 4 new).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/runner.py \
        packages/parcel-shell/tests/test_workflows_runner.py
git commit -m "feat(shell): runner returns WorkflowOutcome; supports attempt kwarg"
```

---

## Task 4: Worker handlers — raise `arq.Retry` on error+budget

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/worker.py`
- Modify: `packages/parcel-shell/tests/test_workflows_worker.py`

- [ ] **Step 1: Append failing tests to `test_workflows_worker.py`**

```python
async def test_run_event_dispatch_no_retry_when_max_retries_zero(
    sessionmaker_factory, monkeypatch
) -> None:
    """An erroring action with max_retries=0 does NOT raise Retry."""
    from arq import Retry

    wf = Workflow(
        slug="bad",
        title="B",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(UpdateField(field="x", value=1),),  # subject_id is None -> raises
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload = [{"event": "a", "subject_ref": None, "subject_id": None, "changed": []}]
    ctx = {"sessionmaker": sessionmaker_factory, "job_try": 1}

    # No exception expected.
    await run_event_dispatch(ctx, payload)


async def test_run_event_dispatch_raises_retry_on_error_with_budget(
    sessionmaker_factory, monkeypatch
) -> None:
    from arq import Retry

    wf = Workflow(
        slug="bad",
        title="B",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(UpdateField(field="x", value=1),),
        max_retries=2,
        retry_backoff_seconds=10,
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload = [{"event": "a", "subject_ref": None, "subject_id": None, "changed": []}]
    ctx = {"sessionmaker": sessionmaker_factory, "job_try": 1}

    with pytest.raises(Retry) as exc_info:
        await run_event_dispatch(ctx, payload)
    assert exc_info.value.defer is not None
    # try=1 -> defer = 10 * 2**0 = 10s
    assert exc_info.value.defer.total_seconds() == 10.0


async def test_run_event_dispatch_no_retry_when_budget_exhausted(
    sessionmaker_factory, monkeypatch
) -> None:
    """job_try=3 with max_retries=2: budget exhausted, no Retry raised."""
    wf = Workflow(
        slug="bad",
        title="B",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(UpdateField(field="x", value=1),),
        max_retries=2,
        retry_backoff_seconds=10,
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload = [{"event": "a", "subject_ref": None, "subject_id": None, "changed": []}]
    ctx = {"sessionmaker": sessionmaker_factory, "job_try": 3}

    # job_try (3) > max_retries (2) — budget exhausted.
    await run_event_dispatch(ctx, payload)


async def test_run_event_dispatch_writes_audit_with_job_try_attempt(
    sessionmaker_factory, monkeypatch
) -> None:
    """job_try=2 → audit row with attempt=2."""
    from sqlalchemy import select

    wf = Workflow(
        slug="t",
        title="T",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("hi"),),
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload = [{"event": "a", "subject_ref": None, "subject_id": None, "changed": []}]
    ctx = {"sessionmaker": sessionmaker_factory, "job_try": 2}
    await run_event_dispatch(ctx, payload)

    async with sessionmaker_factory() as s:
        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].attempt == 2


async def test_run_scheduled_workflow_raises_retry_on_error_with_budget(
    sessionmaker_factory, monkeypatch
) -> None:
    from arq import Retry

    wf = Workflow(
        slug="daily",
        title="D",
        permission="x.read",
        triggers=(OnSchedule(hour=9, minute=0),),
        actions=(UpdateField(field="x", value=1),),  # always fails
        max_retries=1,
        retry_backoff_seconds=30,
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    ctx = {"sessionmaker": sessionmaker_factory, "app": fake_app, "job_try": 1}
    with pytest.raises(Retry):
        await run_scheduled_workflow(ctx, "demo", "daily")
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker.py -v -k "retry or job_try"
```

Expected: tests fail because handlers don't yet raise.

- [ ] **Step 3: Add retry logic to handlers**

Edit `packages/parcel-shell/src/parcel_shell/workflows/worker.py`. Add imports:

```python
from datetime import timedelta

from arq import Retry
```

Replace `run_event_dispatch`:

```python
async def run_event_dispatch(ctx: dict, payload: list[dict[str, Any]]) -> None:
    """Re-fetch subjects, dispatch events, raise arq.Retry on error+budget."""
    sessionmaker = ctx["sessionmaker"]
    job_try = ctx.get("job_try", 1)

    async with sessionmaker() as session:
        events = [await decode_event(p, session) for p in payload]

    # We raise Retry as soon as ANY workflow errors with budget remaining.
    # Multi-event payloads with mixed success/failure will re-run successful
    # workflows on retry — known imprecision, see spec "Risks".
    for ev in events:
        registered = collect_workflows(_active_app)
        for r in registered:
            if any(_matches(t, ev) for t in r.workflow.triggers):
                outcome = await run_workflow(
                    r.module_name, r.workflow, ev, sessionmaker, attempt=job_try
                )
                if outcome.status == "error" and job_try <= r.workflow.max_retries:
                    delay = r.workflow.retry_backoff_seconds * 2 ** (job_try - 1)
                    raise Retry(defer=timedelta(seconds=delay))
```

Replace `run_scheduled_workflow`:

```python
async def run_scheduled_workflow(ctx: dict, module_name: str, slug: str) -> None:
    """Cron-fired workflow run; raise arq.Retry on error+budget."""
    sessionmaker = ctx["sessionmaker"]
    fake_app = ctx["app"]
    registered = collect_workflows(fake_app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None:
        _log.warning("workflows.scheduled.unknown", module=module_name, slug=slug)
        return

    job_try = ctx.get("job_try", 1)
    ev = {
        "event": f"{module_name}.{slug}.scheduled",
        "subject": None,
        "subject_id": None,
        "changed": (),
    }
    outcome = await run_workflow(
        module_name, hit.workflow, ev, sessionmaker, attempt=job_try
    )
    if outcome.status == "error" and job_try <= hit.workflow.max_retries:
        delay = hit.workflow.retry_backoff_seconds * 2 ** (job_try - 1)
        raise Retry(defer=timedelta(seconds=delay))
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker.py -v
```

Expected: 10 passed (5 from 10b + 5 new).

- [ ] **Step 5: Run the broader workflow test suite to confirm no regressions**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py \
              packages/parcel-shell/tests/test_workflows_runner.py \
              packages/parcel-shell/tests/test_workflows_routes.py \
              packages/parcel-shell/tests/test_workflows_worker.py \
              packages/parcel-shell/tests/test_workflows_serialize.py \
              packages/parcel-shell/tests/test_workflows_sidebar.py \
              packages/parcel-shell/tests/test_workflows_boot_validation.py -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/worker.py \
        packages/parcel-shell/tests/test_workflows_worker.py
git commit -m "feat(shell): worker handlers raise arq.Retry on error+budget"
```

---

## Task 5: Audit detail UI — `Attempt` column

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/detail.html`

- [ ] **Step 1: Edit the template**

Find the audits `<table>` block and add a column. The existing `<thead>`/`<tbody>` looks like:

```html
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
        ...
```

Insert `Attempt` between `Subject` and `Status`:

```html
<thead class="bg-gray-50 text-xs uppercase text-gray-600">
  <tr>
    <th class="text-left p-2">When</th>
    <th class="text-left p-2">Event</th>
    <th class="text-left p-2">Subject</th>
    <th class="text-left p-2">Attempt</th>
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
      <td class="p-2">{{ a.attempt }}</td>
      <td class="p-2">
        ...
```

- [ ] **Step 2: Verify the existing route tests still render the page**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_routes.py::test_detail_renders_with_permission -v
```

Expected: PASS (the test asserts content; adding a column doesn't break the assertions).

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/templates/workflows/detail.html
git commit -m "feat(shell): show Attempt column in workflow audit detail"
```

---

## Task 6: ARQ end-to-end retry integration test

**Files:**
- Modify: `packages/parcel-shell/tests/test_workflows_worker_integration.py`

- [ ] **Step 1: Append the retry test**

```python
async def test_worker_round_trip_retries_on_error(
    redis_container: str, sessionmaker_factory, monkeypatch
) -> None:
    """A workflow with max_retries=2 + always-failing action produces 3 audit rows
    (attempt=1, 2, 3) when run end-to-end through ARQ."""
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)

    wf = Workflow(
        slug="bad",
        title="B",
        permission="x.read",
        triggers=(OnCreate("integration.test.retry"),),
        actions=(UpdateField(field="x", value=1),),  # always raises
        max_retries=2,
        retry_backoff_seconds=1,  # keep test fast
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf,))
            }
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    redis_settings = RedisSettings.from_dsn(redis_container)
    pool = await create_pool(redis_settings)
    try:
        payload = encode_events(
            [
                {
                    "event": "integration.test.retry",
                    "subject": None,
                    "subject_id": None,
                    "changed": (),
                }
            ]
        )
        await pool.enqueue_job("run_event_dispatch", payload)
    finally:
        await pool.close()

    from parcel_shell.workflows.worker import (
        run_event_dispatch,
        run_scheduled_workflow,
    )

    async def _test_startup(ctx: dict) -> None:
        ctx["sessionmaker"] = sessionmaker_factory
        ctx["app"] = fake_app
        runner.set_active_app(fake_app)

    async def _test_shutdown(ctx: dict) -> None:
        return None

    worker = Worker(
        functions=[run_event_dispatch, run_scheduled_workflow],
        redis_settings=redis_settings,
        on_startup=_test_startup,
        on_shutdown=_test_shutdown,
        burst=True,
        max_jobs=1,
        # Crucial: ARQ's max_tries default (5) accommodates our 3 attempts.
    )
    try:
        # 3 attempts × ~1-2s backoff each = comfortably under 30s.
        await asyncio.wait_for(worker.async_run(), timeout=30.0)
    finally:
        await worker.close()

    async with sessionmaker_factory() as s:
        rows = (await s.scalars(select(WorkflowAudit).order_by(WorkflowAudit.attempt))).all()
        assert len(rows) == 3, f"expected 3 attempts, got {len(rows)}"
        assert [r.attempt for r in rows] == [1, 2, 3]
        assert all(r.status == "error" for r in rows)
        assert all(r.workflow_slug == "bad" for r in rows)
```

(Add `UpdateField` and `OnCreate` to the existing `parcel_sdk` import at the top of the file if not already present.)

- [ ] **Step 2: Run the integration test**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker_integration.py -v
```

Expected: 2 passed (the existing test + the new retry test).

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/test_workflows_worker_integration.py
git commit -m "test(shell): e2e ARQ retry — 3 audit rows on max_retries=2"
```

---

## Task 7: Documentation

**Files:**
- Modify: `docs/module-authoring.md`
- Modify: `CLAUDE.md`
- Modify: `docs/index.html`

- [ ] **Step 1: Add a "Retries" subsection to `module-authoring.md`**

Find the "Failure semantics" subsection inside the "Workflows" section. Insert a new "Retries" subsection right after it:

````markdown
### Retries (Phase 10b-retry)

Workflows opt into retry by setting two fields:

```python
welcome = Workflow(
    slug="webhook_callback",
    title="Webhook callback",
    permission="x.write",
    triggers=(OnCreate("x.thing.created"),),
    actions=(...),
    max_retries=3,                # default 0 (no retry)
    retry_backoff_seconds=30,     # default 30; exponential
)
```

When an action chain fails inside the worker:
- If `job_try <= max_retries`, the worker raises `arq.Retry(defer=...)` and ARQ
  re-enqueues the job. Each attempt writes its own audit row with the
  `attempt` column set to the try number (1, 2, 3, ...).
- If `job_try > max_retries`, the audit row is the final record and ARQ
  does not retry.

The delay between attempts is `retry_backoff_seconds * 2 ** (current_try - 1)`.
For default `retry_backoff_seconds=30`: try 2 = 30s, try 3 = 60s, try 4 = 120s.

**Idempotency:** Action chains run again from scratch on retry. If your
`UpdateField` actions or your custom action data fns have side effects,
ensure they're idempotent or guarded against duplicate execution. The audit
log shows you which attempt is which.

**Inline mode (tests + `parcel dev`) does not retry.** `PARCEL_WORKFLOWS_INLINE=1`
short-circuits the queue entirely; failing workflows write a single audit row
with `attempt=1`. Tests that exercise retry semantics use the
testcontainer-Redis end-to-end harness (see
`packages/parcel-shell/tests/test_workflows_worker_integration.py`).

**Multi-event imprecision.** If a single `_on_after_commit` payload fires
multiple events and one workflow errors (with retry budget) while another
succeeds, the whole job re-runs — the successful workflow runs again on the
next attempt. In practice payloads are usually single-event (one `emit` per
handler), so this is rarely an issue. A cleaner per-(event,workflow)-pair
enqueue lands in 10c if it proves necessary.
````

- [ ] **Step 2: Update `CLAUDE.md`**

Replace the Phase-10b "Current phase" paragraph with a 10b-retry one:

```markdown
**Phase 10b-retry — Workflow retry semantics done.** Workflows opt into retry by setting `Workflow.max_retries: int = 0` (default no retry) and `Workflow.retry_backoff_seconds: int = 30` (default base for exponential backoff). When an action chain fails in the worker, the handler reads `ctx["job_try"]` (ARQ-provided), passes it to `run_workflow` as `attempt`, and on `outcome.status == "error"` AND `job_try <= max_retries` raises `arq.Retry(defer=timedelta(seconds=base * 2 ** (job_try - 1)))`. ARQ re-enqueues with `job_try += 1`. Each attempt writes its own audit row with the new `attempt` column (migration 0008, additive `NOT NULL DEFAULT 1`). `run_workflow` now returns a `WorkflowOutcome(status, error_message, failed_action_index)` dataclass so the worker can decide retry without re-parsing audit. Inline mode (`PARCEL_WORKFLOWS_INLINE=1`) does not retry — no queue. Audit detail UI gains an `Attempt` column. SDK bumped to `0.8.0` (adds two `Workflow` fields with construction-time validation: `max_retries >= 0`, `retry_backoff_seconds >= 1`). Existing 10a/10b workflows are unchanged (default `max_retries=0` keeps the audit-once-on-error invariant). Test count: 417 → ~429 (one new e2e ARQ retry test confirms 3 audit rows for `max_retries=2`).

Next: **Phase 10c — Workflows rich actions** (`send_email`, `call_webhook`, `run_module_function`, `generate_report` action types; per-action capability declarations; richer audit UI with status/event/module filters and a manual-retry button). Start a new session; prompt: "Begin Phase 10c per `CLAUDE.md` roadmap." The full upcoming roadmap (10b-retry ✅ → 10c → 11) is described below under "Upcoming phases".
```

In the **Locked-in decisions** table, append:

```markdown
| Workflow retry policy | Opt-in via `Workflow.max_retries: int = 0` and `Workflow.retry_backoff_seconds: int = 30`. Validated at SDK construction time (`max_retries >= 0`, `retry_backoff_seconds >= 1`). Default 0 keeps existing 10a/10b workflows unchanged. |
| Workflow retry mechanics | Worker handlers consult `ctx["job_try"]` (ARQ-provided), pass as `attempt` to `run_workflow`, and on `status="error"` + budget remaining raise `arq.Retry(defer=timedelta(seconds=base * 2 ** (job_try - 1)))`. Exponential backoff; no upper cap. Each attempt writes its own audit row. Inline mode does not retry. |
| Workflow audit attempt column | New `attempt: int NOT NULL DEFAULT 1` on `shell.workflow_audit` (migration 0008). Audit detail UI surfaces it as a sortable column. Audit rows for a single logical event ordered chronologically by `created_at` form the retry sequence (1 → 2 → 3 → ...). |
| Workflow run_workflow return | `WorkflowOutcome(status, error_message, failed_action_index)` frozen dataclass. Audit row is still written internally in a separate session; the return value lets worker handlers make retry decisions without re-querying. |
```

In the **Phased roadmap** table, change `10b-retry` from `⏭ next` to `✅ done`, and surface 10c as the next phase:

```markdown
| 10b-retry | ✅ done | Per-workflow max_retries + exponential backoff (small phase) |
| 10c | ⏭ next | Workflows rich actions (send_email, call_webhook, run_module_function, generate_report) + richer UI |
```

In the **Upcoming phases** section, mark 10b-retry shipped:

```markdown
### Phase 10b-retry — Workflow retry semantics ✅ shipped

Shipped on the `phase-10b-retry` branch. See the four "Workflow retry *" rows added in this phase under "Locked-in decisions" for the concrete contracts. Opt-in via `Workflow.max_retries` (default 0) + `Workflow.retry_backoff_seconds` (default 30, exponential). Worker handlers raise `arq.Retry` when `status="error"` and `job_try <= max_retries`. Audit rows gain an `attempt` column (migration 0008). `run_workflow` returns a `WorkflowOutcome` dataclass. Inline-mode tests do not retry; e2e retry coverage rides on the testcontainer-Redis worker integration test.
```

(Remove the old `### Phase 10b-retry` "scope" block since it's now shipped.)

- [ ] **Step 3: Update the website**

Edit `docs/index.html`. Update the hero stat-line:

```html
    <div class="stat-line"><span class="dot"></span> Phases 1–9 + 10a + 10b + 10b-retry complete: shell, auth + RBAC, modules, admin UI, Contacts, SDK + CLI, gate + sandbox, Claude generator + chat, dashboards, reports, and workflows (sync triggers, scheduled cron, ARQ worker, retry semantics, audit log, read-only UI). Phase 10c (rich actions + richer UI) up next; sandbox preview enrichment (11) follows.</div>
```

Update the roadmap. Replace the existing `10b-retry` row:

```html
      <li>
        <span class="phase-num">10b-retry</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">Workflows: per-workflow max_retries + exponential backoff on top of ARQ's queue</span>
      </li>
      <li>
        <span class="phase-num">10c</span>
        <span class="phase-status next">⏭ next</span>
        <span class="phase-goal">Workflows: rich actions — send_email, call_webhook, run_module_function, generate_report; richer audit UI</span>
      </li>
```

Update the test count line:

```html
<pre><code>uv run pytest                              <span style="color: var(--fg-muted)"># 429 tests, ~155s</span></code></pre>
```

- [ ] **Step 4: Final lint + test pass**

```bash
uv run ruff check
uv run ruff format
uv run pyright
uv run pytest -q
```

Expected: green; ~429 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/module-authoring.md CLAUDE.md docs/index.html
git commit -m "docs: phase 10b-retry authoring guide + CLAUDE.md + website update"
```

---

## Task 8: Final verification + push

- [ ] **Step 1: Run full suite one last time**

```bash
uv run pytest -q
```

Expected: ~429 passed.

- [ ] **Step 2: Push branch**

```bash
git push -u origin phase-10b-retry
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --title "Phase 10b-retry: Workflow retry semantics" --body "..."
```

(Body modeled on the Phase 10b PR — summary, what shipped, spec deviations (none), test plan.)

---

## Self-review checklist

- [x] **Spec coverage:** every locked decision has a task — `Workflow.max_retries`/`retry_backoff_seconds` + validation (Task 1), migration 0008 + `attempt` column (Task 2), `WorkflowOutcome` + `run_workflow(attempt=)` (Task 3), worker-handler retry decision (Task 4), audit detail UI (Task 5), e2e retry test (Task 6), docs (Task 7).
- [x] **Placeholder scan:** no "TBD" / "implement later". Every code step shows complete code.
- [x] **Type consistency:** `WorkflowOutcome(status, error_message, failed_action_index)` matches across runner module, runner tests, worker handlers, worker tests. `attempt: int` matches across SDK validation, model column, runner kwarg, worker `ctx["job_try"]` pass-through, audit row, and template column.
- [x] **Spec deviations:** none flagged at top.

---

**Plan complete. Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.
