# Phase 10b-retry — Workflow per-task retry semantics

**Status:** approved
**Date:** 2026-04-25
**Builds on:** Phase 10b (ARQ + worker container).
**Splits into:** Phase 10c (rich actions + richer UI).

## Goal

Add opt-in retry semantics to workflows. Module authors set `Workflow.max_retries=N` and (optionally) `Workflow.retry_backoff_seconds=...`; when an action chain fails inside the worker, the handler raises `arq.Retry(defer=...)` to re-enqueue the job. Audit rows now carry an `attempt: int` column so operators can see the retry history. Inline-mode (test/dev) does not retry — it has no queue.

## Non-goals (10b-retry)

- **Manual "retry now" button** in the audit UI — 10c.
- **Per-action retry** — only workflow-level. An action chain is the unit of retry.
- **Dead-letter queue** — when retries exhaust, the final failure is just the last audit row (`status="error"`, `attempt = max_retries + 1`). No DLQ.
- **Cap on audit-row growth** — high-retry workflows can grow the audit table; retention is still a 10c+ concern.
- **Per-attempt notification webhooks** — 10c+.
- **Configurable backoff strategies** — only exponential is supported. `retry_backoff_seconds` is the base; `delay = base * 2 ** (current_try - 1)`. No linear/jitter/capped options.

## Locked decisions

| Area | Decision |
|---|---|
| Phase scope | Single small phase. Adds `Workflow.max_retries`, `Workflow.retry_backoff_seconds`, `WorkflowAudit.attempt`, migration 0008, and worker-handler retry logic. |
| Default retry policy | Opt-in: `max_retries: int = 0` on the SDK `Workflow` dataclass. Existing 10a/10b workflows are unchanged — any failure still produces exactly one audit row with `status="error"` and `attempt=1`. |
| Backoff | Exponential, base `Workflow.retry_backoff_seconds: int = 30`. Computed as `base * 2 ** (current_try - 1)`. For try 2 = 30s, try 3 = 60s, try 4 = 120s. No upper cap; modules pick a smaller base if needed. |
| Audit row strategy | One row per attempt. New `attempt: int NOT NULL DEFAULT 1` column on `shell.workflow_audit` (migration 0008). |
| `run_workflow` return | Refactored to return `WorkflowOutcome(status, error_message, failed_action_index)`. Audit is still written inside the function (separate session) — the return value is for the caller's retry decision. |
| Worker behaviour | `run_event_dispatch`, `run_scheduled_workflow`, and the per-cron wrappers all read `ctx["job_try"]` (ARQ-provided), call `run_workflow(..., attempt=ctx["job_try"])`, and on `outcome.status == "error"` AND `ctx["job_try"] <= workflow.max_retries` raise `arq.Retry(defer=timedelta(seconds=delay))`. |
| Inline mode | `_dispatch_inline` calls `run_workflow(..., attempt=1)`; no retry possible (no queue). Documented in `module-authoring.md`: "tests run inline; retries only fire under the worker." |
| Inline-mode runner | `dispatch_events(events, sessionmaker)` — the existing inline path — passes `attempt=1` to `run_workflow`. Unchanged for the no-retry case. |
| ARQ `max_tries` | NOT used. ARQ's built-in retry counter is for transient infrastructure failures (Redis disconnects, etc.). Workflow retries are explicit business logic — we raise `Retry` ourselves. We do NOT set `max_tries` on the cron jobs. ARQ's default of 5 is fine; our retry exception explicitly carries `defer` and increments `job_try`. |
| `WorkflowOutcome` shape | Frozen dataclass: `status: str` (`"ok"` \| `"error"`), `error_message: str \| None`, `failed_action_index: int \| None`. Lives in `parcel_shell.workflows.runner`. |
| `run_workflow` signature | Adds `attempt: int = 1` keyword-only argument. Audit row's `attempt` column comes from this. |
| SDK version | 0.7.0 → **0.8.0** (adds `Workflow.max_retries`, `Workflow.retry_backoff_seconds`). |
| Contacts version | Unchanged. Reference workflows don't opt into retry. |
| Audit detail UI | Add an `Attempt` column to `detail.html`'s recent-invocations table. Renders the integer; for 1, shows "1" (the dominant case); for >1, the user sees "2", "3" etc. and understands these are retries. |
| Documentation | `module-authoring.md` "Workflows" section gains a "Retries" subsection; `CLAUDE.md` rolls 10b-retry to ✅, adds locked-decisions block, updates current-phase + next-phase pointer (Phase 10c). |

## Architecture

```
parcel_shell/
  workflows/
    runner.py                    # WorkflowOutcome dataclass + run_workflow returns it
    worker.py                    # handlers consult outcome + raise arq.Retry
    bus.py                       # _dispatch_inline passes attempt=1
    models.py                    # WorkflowAudit gains `attempt` column
  alembic/versions/
    0008_workflow_audit_attempt.py   # migration
parcel-sdk/
  workflows.py                   # Workflow gains max_retries + retry_backoff_seconds
```

No new files. All edits to existing modules.

## SDK changes

```python
# parcel_sdk/workflows.py — Workflow dataclass:

@dataclass(frozen=True, kw_only=True)
class Workflow:
    slug: str
    title: str
    permission: str
    triggers: tuple[Trigger, ...]
    actions: tuple[Action, ...]
    description: str = ""
    max_retries: int = 0                  # 0 = no retry. Opt-in.
    retry_backoff_seconds: int = 30       # base for exponential backoff
```

`__post_init__` validates `max_retries >= 0` and `retry_backoff_seconds >= 1` (raises ValueError on construction).

## Migration 0008

```python
# packages/parcel-shell/src/parcel_shell/alembic/versions/0008_workflow_audit_attempt.py

revision = "0008"
down_revision = "0007"

def upgrade() -> None:
    op.add_column(
        "workflow_audit",
        sa.Column(
            "attempt",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        schema="shell",
    )


def downgrade() -> None:
    op.drop_column("workflow_audit", "attempt", schema="shell")
```

`WorkflowAudit.attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))`.

## Runner changes

```python
# parcel_shell/workflows/runner.py — adds:

@dataclass(frozen=True)
class WorkflowOutcome:
    status: str  # "ok" | "error"
    error_message: str | None
    failed_action_index: int | None


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
    # ... existing chain-execution logic ...
    # When writing audit row:
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
            attempt=attempt,            # NEW
        )
    )
    return WorkflowOutcome(
        status=status,
        error_message=error_message,
        failed_action_index=failed_idx,
    )
```

`dispatch_events(events, sessionmaker)` — the inline path — calls `run_workflow(..., attempt=1)` (the default). No retry; failures audit once and move on.

## Worker handler changes

```python
# parcel_shell/workflows/worker.py

from datetime import timedelta
from arq import Retry


async def run_event_dispatch(ctx: dict, payload: list[dict[str, Any]]) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        events = [await decode_event(p, session) for p in payload]

    job_try = ctx.get("job_try", 1)

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


async def run_scheduled_workflow(ctx: dict, module_name: str, slug: str) -> None:
    sessionmaker = ctx["sessionmaker"]
    fake_app = ctx["app"]
    registered = collect_workflows(fake_app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None:
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

The per-cron wrapper (`_make_cron_handler`) inherits this by calling `run_scheduled_workflow`.

**Important nuance:** `run_event_dispatch` was previously a single dispatch over all events. With retries, we need to be careful: if events have different workflows with different retry policies, raising `Retry` re-enqueues the WHOLE job — i.e., all events in the payload re-run. For 10b-retry's MVP, this is acceptable: in practice, each `_on_after_commit` produces one event payload corresponding to one user action, with usually one or two events. If a multi-event payload turns out to be problematic in production, 10c can split into per-event jobs.

The current code dispatches all matching workflows for all events; we keep that, but add: as soon as ANY workflow in the loop fails AND has retries available, raise. This is a slight imprecision — a multi-workflow payload with mixed success/failure will re-run the successful ones too. Documented as a known limitation.

A cleaner alternative considered: split each (event, workflow) pair into its own ARQ job at enqueue time. That changes the bus surface (one job per event-workflow pair instead of one per event-batch). Defer to 10c if needed.

## Inline-mode behaviour

```python
# parcel_shell/workflows/bus.py — _dispatch_inline (existing function)

def _dispatch_inline(events, sessionmaker, loop):
    # Calls dispatch_events which calls run_workflow with default attempt=1.
    # No retry available — no queue, no Retry exception bubbling up.
    loop.create_task(dispatch_events(events, sessionmaker))
```

Test code that wants to exercise retries uses the testcontainer-Redis end-to-end harness. The unit tests for `run_workflow` (passing `attempt=N`) still work and assert the audit row's `attempt` value.

## Audit detail UI

`detail.html`'s recent-invocations `<table>` gets one new column:

```html
<thead>
  <tr>
    <th>When</th>
    <th>Event</th>
    <th>Subject</th>
    <th>Attempt</th>     <!-- NEW -->
    <th>Status</th>
    <th>Notes</th>
  </tr>
</thead>
<tbody>
  {% for a in audits %}
    <tr>
      <td>{{ a.created_at.strftime("%Y-%m-%d %H:%M:%S") }}</td>
      <td><code class="text-xs">{{ a.event }}</code></td>
      <td><code class="text-xs">{{ a.subject_id or "—" }}</code></td>
      <td>{{ a.attempt }}</td>      <!-- NEW -->
      <td>...</td>
      <td>...</td>
    </tr>
  {% endfor %}
</tbody>
```

Audit rows are already ordered by `created_at desc`, so a retry sequence (attempt 1 → 2 → 3) appears as three consecutive rows in the table.

## Tests

Target: ~12 new tests; ~429 total.

**SDK** (`packages/parcel-sdk/tests/test_workflows.py`)
- `Workflow.max_retries` defaults to `0`.
- `Workflow.retry_backoff_seconds` defaults to `30`.
- `Workflow(max_retries=-1)` raises `ValueError`.
- `Workflow(retry_backoff_seconds=0)` raises `ValueError`.

**Migration 0008** (`packages/parcel-shell/tests/test_migrations_0008.py`)
- After upgrade, `attempt` column exists on `shell.workflow_audit`.
- Existing rows have `attempt=1` (server_default).
- Downgrade drops the column cleanly.

**Runner** (`packages/parcel-shell/tests/test_workflows_runner.py` extension)
- `run_workflow(..., attempt=2)` writes an audit row with `attempt=2`.
- Default `attempt=1` is preserved when caller omits the kwarg.
- Returns a `WorkflowOutcome` with the same `status` / `error_message` / `failed_action_index` as the audit.

**Worker handlers** (`packages/parcel-shell/tests/test_workflows_worker.py` extension)
- `run_event_dispatch` with a `max_retries=0` workflow that errors does NOT raise `Retry`.
- `run_event_dispatch` with `max_retries=2` + `job_try=1` + erroring action raises `Retry` with `defer ≈ 30s`.
- `run_event_dispatch` with `max_retries=2` + `job_try=3` + erroring action does NOT raise (budget exhausted; final attempt audited).
- `run_scheduled_workflow` with `max_retries=1` + `job_try=1` + erroring action raises `Retry` with `defer ≈ 30s`.

**End-to-end ARQ + retries** (`packages/parcel-shell/tests/test_workflows_worker_integration.py` extension)
- Submit a workflow that always errors with `max_retries=2`. Run worker in burst mode for ~20 seconds (enough for ARQ to retry twice). Assert exactly 3 audit rows with `attempt=1`, `2`, `3`, all `status="error"`.

## Documentation

- `docs/module-authoring.md` "Workflows" section — new "Retries" subsection covering the two new fields, the exponential backoff formula, the inline-mode caveat, and a worked example (e.g. a webhook-call workflow with `max_retries=3`).
- `CLAUDE.md` — flip 10b-retry to ✅; add a locked-decisions block; rewrite Current phase paragraph; update Next pointer to Phase 10c. Roadmap row updated.
- `docs/index.html` — flip 10b-retry to ✅, set 10c as next.

## Migration / compatibility

- One new shell migration (0008) — additive (single column, NOT NULL with server_default so existing rows backfill cleanly).
- SDK 0.8.0 — additive: existing `Workflow(...)` calls keep working with their two new fields defaulted.
- No worker restart semantics change; existing workflows behave identically (max_retries=0 by default).
- Inline mode unchanged.

## Risks and follow-ups

- **Audit-row growth.** A workflow with `max_retries=10` that always fails writes 11 audit rows per logical event. No retention. Acceptable for MVP; 10c+ can add a retention setting.
- **Multi-event payload retry.** If an event payload contains multiple events and one fails, raising `Retry` re-runs the whole payload. In practice payloads are usually single-event (one `emit` per handler); documented as a known imprecision. Cleanest fix in 10c: enqueue one job per (event, workflow) pair.
- **`ctx["job_try"]` semantics.** ARQ provides this on every job. We rely on it for the `attempt` value. If ARQ ever changes the key name, we break; pinned `arq>=0.26,<1.0` makes this a controlled risk.
- **Backoff calculation can produce huge delays.** `30 * 2^9 = 15360s ≈ 4.3 hours` for `max_retries=10`. Documented; modules choosing high `max_retries` should pick a smaller base.
- **Inline mode + retry mismatch.** A workflow with `max_retries=3` running under `parcel dev` (inline mode) gets a single attempt, no retry. Tests using `PARCEL_WORKFLOWS_INLINE=1` won't exercise retry semantics. Documented prominently in `module-authoring.md`.
- **AI-generator awareness.** Phase 11's static-analysis gate will need to validate `max_retries >= 0` and `retry_backoff_seconds >= 1`. Both are also enforced at SDK construction time, so the gate's job is just preventing AI-generated workflows from setting absurdly high values. Tracked alongside existing follow-ups.

## Open during implementation

None. All decisions are locked.
