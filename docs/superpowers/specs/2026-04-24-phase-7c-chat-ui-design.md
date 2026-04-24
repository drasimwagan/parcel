# Phase 7c — AI Chat UI — Design Spec

**Date:** 2026-04-24
**Status:** Drafted, approved during brainstorming
**Roadmap:** Phase 7 decomposed. 7a ✅ gate + sandbox. 7b ✅ Claude generator. **7c = chat UI only.** Preview work (sample records, view screenshots) moves to Phase 8.

## Goal

Browser-visible chat surface on top of Phase 7b's generator. Admin types a prompt, watches status, iterates. Each session persists across browser reloads and process restarts so iteration actually works — the whole reason we decomposed Phase 7.

## Non-goals

- **No preview enrichment.** Sample-record seeding, view screenshots, Playwright — all Phase 8.
- **No streaming.** HTMX polling. Token-by-token UI is a later polish item.
- **No accumulated conversation context.** Each admin turn is an independent generation. "Conversational" is a UX pattern, not a model-context pattern.
- **No ARQ / worker process.** Inline `asyncio.create_task` with a boot-time scan that marks orphaned turns as failed.
- **No JSON API for sessions.** HTML endpoints only; sessions JSON defers. 7b's `POST /admin/ai/generate` one-shot stays untouched.
- **No cross-admin visibility.** A session's owner is the only admin who sees it.

## Decisions locked in during brainstorming

| # | Decision |
|---|---|
| Q1 | 7c = chat UI only. Preview (sample data, screenshots) → Phase 8. |
| Q2a | HTMX polling, no SSE/WebSocket. |
| Q2b | Persistent sessions in Postgres (`shell.ai_sessions` + `shell.ai_turns`). |
| Q2c | Each admin turn is an independent generation — no accumulated Claude context across turns. |
| Q3 | Background task via `asyncio.create_task`, own sessionmaker, startup scan → mark orphaned `generating` turns as `failed`. |
| Q4 | No new permissions — `ai.generate` covers chat flow; sessions are per-owner. |
| Q5 | HTML-only for 7c. Keep 7b's JSON one-shot. Sessions JSON defers. |
| Q6 | Polling fragment = full turn-list partial. `hx-trigger="every 1s"` while any turn is `generating`; stops when all terminal. |
| Q7 | Two new tables, migration 0006. |

---

## Database

### `shell.ai_sessions`

```
id                UUID PK
owner_id          UUID FK → shell.users.id (CASCADE on delete)
title             TEXT — first ~40 chars of first prompt, fallback "(untitled)"
created_at        TIMESTAMPTZ
updated_at        TIMESTAMPTZ — bumped whenever a turn is added or updated
```

Index on `owner_id, updated_at DESC`.

### `shell.ai_turns`

```
id                UUID PK
session_id        UUID FK → shell.ai_sessions.id (CASCADE)
idx               INT NOT NULL — 1-indexed position within session
prompt            TEXT NOT NULL
status            TEXT NOT NULL — 'generating' | 'succeeded' | 'failed'
sandbox_id        UUID NULL FK → shell.sandbox_installs.id (SET NULL on sandbox delete)
failure_kind      TEXT NULL — 'provider_error' | 'no_files' | 'gate_rejected' | 'exceeded_retries' | 'process_restart'
failure_message   TEXT NULL
gate_report       JSONB NULL — serialized GateReport when kind indicates gate rejection
started_at        TIMESTAMPTZ NOT NULL
finished_at       TIMESTAMPTZ NULL
```

Unique `(session_id, idx)`. Index on `session_id, idx`. Index on `status` (so the boot scan for orphans is O(small)).

**Migration 0006** creates both tables.

---

## Service layer

New `parcel_shell.ai.chat` submodule:

```
parcel_shell/ai/chat/
  __init__.py
  models.py          # AISession, AITurn
  service.py         # create_session, add_turn, update_turn_*, list_sessions, sweep_orphans
  schemas.py         # (small — HTML-only for 7c, but typed DTOs help tests)
```

**Public service functions** (all async, take `db: AsyncSession`):

- `create_session(db, owner_id) -> AISession` — new row with empty title.
- `add_turn(db, session_id, prompt) -> AITurn` — writes a `generating` row with the next `idx`, sets session `title` from the first prompt if title is empty, bumps `updated_at`.
- `mark_succeeded(db, turn_id, sandbox_id) -> None`
- `mark_failed(db, turn_id, kind, message, gate_report=None) -> None`
- `list_sessions_for_owner(db, owner_id, limit=50) -> list[AISession]`
- `get_session(db, session_id, owner_id) -> AISession | None` — enforces ownership; returns None (caller maps to 404) if the session exists but belongs to someone else.
- `get_turns(db, session_id) -> list[AITurn]` — ordered by `idx`.
- `sweep_orphans(db) -> int` — UPDATE any `status='generating'` rows to `failed` with kind `process_restart`. Returns count. Called once at lifespan startup.

The **background task** that runs the actual generation is a module-level coroutine:

```python
# parcel_shell/ai/chat/worker.py
async def run_turn(
    *,
    turn_id: UUID,
    prompt: str,
    provider: ClaudeProvider,
    sessionmaker: async_sessionmaker[AsyncSession],
    app: FastAPI,
    settings: Settings,
) -> None:
    """Background task. Opens its own session, runs generate_module,
    writes the result back to the turn row. Never raises — all errors
    funnel through mark_failed.
    """
```

It catches every exception (including cancellation on shutdown) and ensures the turn row transitions to a terminal state.

---

## HTML routes

New router `parcel_shell/ai/chat/router_ui.py`. Prefix: `/ai` (not `/admin/ai/` — the chat surface is admin-facing but the URL scheme mirrors `/sandbox`, `/modules`, which are top-level).

```
GET  /ai                              → list my sessions + "New session" button
POST /ai/sessions                     → create session, redirect to /ai/sessions/<id>
GET  /ai/sessions/{id}                → full session page (turns + prompt box)
POST /ai/sessions/{id}/turns          → add a turn, kick off background task, redirect to /ai/sessions/{id}
GET  /ai/sessions/{id}/status         → polling partial (full turn-list + prompt box state)
```

Every route requires `ai.generate` permission via `html_require_permission`. `get_session` enforces ownership. If the session doesn't belong to the caller → 404 (not 403 — don't leak session existence to other admins).

**Templates** under `packages/parcel-shell/src/parcel_shell/ui/templates/ai/`:

- `list.html` — table of sessions with title, turn count, last-activity, click-through.
- `detail.html` — extends base. Contains `#turns` div (partial-swappable), a prompt form, `hx-get="/ai/sessions/<id>/status" hx-trigger="every 1s" hx-target="#turns"` while any turn is `generating`.
- `_turns.html` — the partial: renders the full turn list. Each turn shows status pill, prompt, and one of: sandbox link (success), gate-report summary (gate_rejected/exceeded_retries), or the failure message (other).

When the polling fragment is served and *no* turn is still `generating`, it sets `hx-trigger` to nothing (or removes itself from the polled element) so the client stops polling. Easiest implementation: the polling endpoint returns an HTML fragment whose root element includes `hx-trigger="..."` only when polling should continue. HTMX respects `hx-swap-oob` or simply the container re-render.

**Sidebar:** the existing "AI Lab" section grows a new item above Sandbox:

```python
SidebarSection(
    label="AI Lab",
    items=(
        SidebarItem(label="Generator", href="/ai", permission="ai.generate"),
        SidebarItem(label="Sandbox", href="/sandbox", permission="sandbox.read"),
    ),
),
```

---

## Background-task flow

```
POST /ai/sessions/<sid>/turns (form: prompt)
  │
  ▼
add_turn(db, sid, prompt) → AITurn(status='generating', started_at=now)
commit
  │
  ▼
asyncio.create_task(run_turn(turn_id=..., prompt=..., provider=app.state.ai_provider,
                              sessionmaker=app.state.sessionmaker, app=app, settings=settings))
  │
  ▼
303 redirect → /ai/sessions/<sid>  (HTMX follows)

  ╮  (meanwhile, in the task)
  │  open a session via the sessionmaker
  │  try:
  │    result = await generate_module(prompt, provider=..., db=task_db, app=app, settings=settings)
  │    if isinstance(result, SandboxInstall):
  │      await mark_succeeded(task_db, turn_id, sandbox_id=result.id)
  │    else:
  │      await mark_failed(task_db, turn_id, kind=result.kind, message=result.message,
  │                        gate_report=result.gate_report)
  │    await task_db.commit()
  │  except BaseException as exc:      # includes CancelledError
  │    await mark_failed(task_db, turn_id, kind='provider_error',
  │                      message=f'background task crashed: {exc!r}')
  │    await task_db.commit()
  ╯
```

No progress updates mid-generation. The turn row has two writes total: one at `add_turn`, one at finish.

**Startup scan** happens once, after `mount_sandbox_on_boot`:

```python
async with sessionmaker() as s:
    n = await chat_service.sweep_orphans(s)
    await s.commit()
    if n:
        log.warning("ai.chat.orphans_swept", count=n)
```

---

## Test strategy

**~15 new tests.**

- `test_chat_service.py` — unit tests for `create_session`, `add_turn`, `mark_succeeded`, `mark_failed`, `sweep_orphans`, ownership enforcement on `get_session`.
- `test_chat_worker.py` — `run_turn` with a `FakeProvider`:
  - Success path → turn transitions to `succeeded` with `sandbox_id`.
  - Gate rejection → turn transitions to `failed` with `kind='exceeded_retries'` and a gate_report payload.
  - Provider error → turn transitions to `failed`.
  - Task cancellation mid-run → turn ends up `failed` (not stuck `generating`).
- `test_chat_routes.py` — HTTP smoke:
  - `GET /ai` returns 200 and the admin's own session shows up.
  - `POST /ai/sessions` creates and redirects.
  - `POST /ai/sessions/<id>/turns` writes a generating turn + returns 303.
  - `GET /ai/sessions/<id>/status` returns the turn-list partial.
  - Cross-admin 404 (admin A creates a session, admin B gets 404 on `/ai/sessions/<A-id>`).

All tests use the `FakeProvider` fixture. No network, no real generation. The background-task tests `await` the created task directly (no polling).

---

## File plan

**Create:**
- `packages/parcel-shell/src/parcel_shell/ai/chat/__init__.py`
- `packages/parcel-shell/src/parcel_shell/ai/chat/models.py`
- `packages/parcel-shell/src/parcel_shell/ai/chat/service.py`
- `packages/parcel-shell/src/parcel_shell/ai/chat/worker.py`
- `packages/parcel-shell/src/parcel_shell/ai/chat/router_ui.py`
- `packages/parcel-shell/src/parcel_shell/ui/templates/ai/list.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/ai/detail.html`
- `packages/parcel-shell/src/parcel_shell/ui/templates/ai/_turns.html`
- `packages/parcel-shell/src/parcel_shell/alembic/versions/0006_ai_chat.py`
- `packages/parcel-shell/tests/test_chat_service.py`
- `packages/parcel-shell/tests/test_chat_worker.py`
- `packages/parcel-shell/tests/test_chat_routes.py`

**Modify:**
- `packages/parcel-shell/src/parcel_shell/app.py` — register chat UI router, call `sweep_orphans` in lifespan.
- `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` — add "Generator" item to "AI Lab" section.
- `CLAUDE.md`, `README.md`, `docs/index.html`, `docs/architecture.md` — document the chat flow, flip 7c to ✅, Phase 8 (preview work) to ⏭ next.

**Delete:** none.

---

## Risks

1. **`asyncio.create_task` swallowed exceptions.** The task's top-level try/except must catch `BaseException` (not just `Exception`) so cancellation at shutdown still transitions the turn. Tests explicitly cover the cancellation path.
2. **Task storage.** We don't keep a reference to the created task anywhere — it's garbage-collected if nothing holds a reference. Pythons <3.11 would drop tasks; 3.12 still will. Fix: stash the task in `app.state.ai_tasks: set[Task]` and discard from `done_callback`. Minor but load-bearing.
3. **Polling after session close.** If the admin leaves the session page open while logged out, HTMX keeps polling and gets a 303 to /login. Acceptable — the response is small and the user closes the tab eventually.
4. **Multiple concurrent turns on the same session.** The UI disables the prompt form while a turn is generating; the backend trusts the UI. If an admin races with two browser tabs, both turns queue and run in parallel (distinct `idx` via `MAX(idx)+1`). No correctness issue, just weird UX. Acceptable for 7c.
5. **Session title leak.** Title is the first ~40 chars of the first prompt; could contain sensitive data. Not logged, shown only to the owner. Fine.
