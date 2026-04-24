# Phase 7c — AI Chat UI — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Ship the chat surface on top of Phase 7b's generator. Persistent sessions, HTMX polling, inline background-task generation. No streaming, no ARQ, no preview enrichment.

**Architecture:** Two new tables (`shell.ai_sessions`, `shell.ai_turns`). Service layer under `parcel_shell.ai.chat`. Background task via `asyncio.create_task` with a boot-time orphan sweep. HTML routes at `/ai/*`. HTMX polls `/ai/sessions/<id>/status` every 1s while any turn is `generating`.

**Spec:** [docs/superpowers/specs/2026-04-24-phase-7c-chat-ui-design.md](../specs/2026-04-24-phase-7c-chat-ui-design.md)

---

### Task 1: Migration 0006 + models

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/chat/__init__.py`
- Create: `packages/parcel-shell/src/parcel_shell/ai/chat/models.py`
- Create: `packages/parcel-shell/src/parcel_shell/alembic/versions/0006_ai_chat.py`

- [ ] **Step 1: Write `models.py`** — `AISession` and `AITurn` SQLAlchemy models bound to `ShellBase`. Columns per spec; `idx` not `index` (reserved-word-ish; also Python stdlib). Status is `Mapped[str]` (Literal used in app code, not as a DB column type).

- [ ] **Step 2: Write migration 0006** — two `op.create_table` calls with indexes. Pattern-copy 0004's structure.

- [ ] **Step 3: Commit** — `feat(ai): ai_sessions + ai_turns tables (migration 0006)`

---

### Task 2: Service layer

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/chat/service.py`
- Create: `packages/parcel-shell/tests/test_chat_service.py`

- [ ] **Step 1: Write failing tests.**
  - `test_create_session_returns_empty_session`
  - `test_add_turn_sets_index_and_title_from_first_prompt`
  - `test_add_turn_increments_index_within_session`
  - `test_mark_succeeded_transitions_turn`
  - `test_mark_failed_records_kind_and_gate_report`
  - `test_get_session_rejects_cross_owner` — admin A creates, admin B's owner_id gets None back.
  - `test_sweep_orphans_marks_generating_as_failed_process_restart`

- [ ] **Step 2: Implement `service.py`** with the functions listed in the spec. All take `db: AsyncSession` and do their writes via `db.add` / `db.execute` / `db.flush`; caller commits.

- [ ] **Step 3: Run tests.** All pass.

- [ ] **Step 4: Commit** — `feat(ai-chat): session + turn service with ownership + orphan sweep`

---

### Task 3: Background worker (`run_turn`)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/chat/worker.py`
- Create: `packages/parcel-shell/tests/test_chat_worker.py`

- [ ] **Step 1: Write failing tests.** Use `FakeProvider` queue:
  - `test_run_turn_success_marks_succeeded` — FakeProvider returns the contacts files → turn row status `succeeded` with `sandbox_id` set.
  - `test_run_turn_gate_rejection_marks_failed_with_report` — FakeProvider returns bad files twice → kind `exceeded_retries`, `gate_report` populated.
  - `test_run_turn_provider_error_marks_failed`.
  - `test_run_turn_catches_unexpected_exception` — FakeProvider raises a random RuntimeError (not ProviderError) → turn still ends up `failed` with the message.

- [ ] **Step 2: Implement `worker.run_turn`.**

```python
async def run_turn(
    *, turn_id, prompt, provider, sessionmaker, app, settings,
) -> None:
    from parcel_shell.ai.chat import service as chat_service
    from parcel_shell.ai.generator import GenerationFailure, generate_module
    from parcel_shell.sandbox.models import SandboxInstall
    try:
        async with sessionmaker() as db:
            result = await generate_module(
                prompt, provider=provider, db=db, app=app, settings=settings,
            )
            if isinstance(result, SandboxInstall):
                await chat_service.mark_succeeded(db, turn_id, sandbox_id=result.id)
            else:
                await chat_service.mark_failed(
                    db, turn_id,
                    kind=result.kind, message=result.message,
                    gate_report=result.gate_report,
                )
            await db.commit()
    except BaseException as exc:  # noqa: BLE001 — must cover CancelledError
        try:
            async with sessionmaker() as db:
                await chat_service.mark_failed(
                    db, turn_id, kind="provider_error",
                    message=f"background task crashed: {exc!r}",
                )
                await db.commit()
        except Exception:  # nosec — best-effort
            _log.exception("ai.chat.worker_cleanup_failed", turn_id=str(turn_id))
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            raise
```

- [ ] **Step 3: Run tests.**

- [ ] **Step 4: Commit** — `feat(ai-chat): background run_turn worker with CancelledError safety net`

---

### Task 4: HTML routes + templates

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/ai/chat/router_ui.py`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/ai/list.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/ai/detail.html`
- Create: `packages/parcel-shell/src/parcel_shell/ui/templates/ai/_turns.html`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`
- Create: `packages/parcel-shell/tests/test_chat_routes.py`

- [ ] **Step 1: Templates.**

`list.html`:
- Extends `_base.html`, uses the standard sidebar.
- Shows a table of my sessions (title, turn count, last activity) + a big "New session" button that submits `POST /ai/sessions`.

`detail.html`:
- Extends `_base.html`.
- Renders the session title as the page header.
- Includes a `<div id="turns">` with `{% include "ai/_turns.html" %}` that carries `hx-get`/`hx-trigger`/`hx-target` attrs only if any turn is still `generating`.
- A prompt form (`<form hx-post="/ai/sessions/<id>/turns">`) disabled when any turn is generating.

`_turns.html`:
- Iterates turns, one card per turn:
  - `generating` → yellow border, spinner, elapsed time.
  - `succeeded` → green border, "Open sandbox →" link to `/sandbox/<sandbox_id>`.
  - `failed` → red border, failure kind pill, failure message, gate-report summary if present.
- Root element is `<div id="turns" hx-get="/ai/sessions/<sid>/status" hx-trigger="every 1s" hx-target="#turns" hx-swap="outerHTML">` **only when** any turn is `generating`; when all terminal, root is just `<div id="turns">` (no polling).

- [ ] **Step 2: Router.**

```python
# router_ui.py
@router.get("/ai")                                  # list my sessions
@router.post("/ai/sessions")                        # create + redirect
@router.get("/ai/sessions/{sid}")                   # detail page
@router.post("/ai/sessions/{sid}/turns")            # add turn + create_task + redirect
@router.get("/ai/sessions/{sid}/status")            # partial turn-list
```

The POST `/turns` handler is the interesting one:

```python
@router.post("/ai/sessions/{sid}/turns")
async def add_turn_endpoint(
    sid: UUID,
    request: Request,
    prompt: str = Form(...),
    user = Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    session_row = await chat_service.get_session(db, sid, owner_id=user.id)
    if session_row is None:
        raise HTTPException(404, "session_not_found")

    turn = await chat_service.add_turn(db, sid, prompt)
    await db.commit()

    provider = request.app.state.ai_provider
    if provider is not None:
        task = asyncio.create_task(
            run_turn(
                turn_id=turn.id, prompt=prompt, provider=provider,
                sessionmaker=request.app.state.sessionmaker,
                app=request.app, settings=request.app.state.settings,
            )
        )
        tasks: set = getattr(request.app.state, "ai_tasks", set())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        request.app.state.ai_tasks = tasks
    else:
        await chat_service.mark_failed(
            db, turn.id, kind="provider_error",
            message="AI provider not configured",
        )
        await db.commit()

    return RedirectResponse(f"/ai/sessions/{sid}", status_code=303)
```

- [ ] **Step 3: Register router in `create_app`** (after existing `ui_sandbox_router`).

- [ ] **Step 4: Update sidebar** — add "Generator" above "Sandbox" under "AI Lab".

- [ ] **Step 5: Write route tests.** See spec's test strategy; all use `FakeProvider` injected via `committing_app.state.ai_provider`.

- [ ] **Step 6: Commit** — `feat(ai-chat): /ai HTML surface with HTMX polling`

---

### Task 5: Lifespan wiring — orphan sweep + task set

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`

- [ ] **Step 1:** In the lifespan, after `mount_sandbox_on_boot`:

```python
from parcel_shell.ai.chat import service as chat_service

async with sessionmaker() as s:
    swept = await chat_service.sweep_orphans(s)
    await s.commit()
    if swept:
        log.warning("ai.chat.orphans_swept", count=swept)

app.state.ai_tasks = set()
```

- [ ] **Step 2:** On shutdown — cancel any outstanding tasks (best-effort):

```python
finally:
    tasks = getattr(app.state, "ai_tasks", set())
    for task in list(tasks):
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    ...existing cleanup...
```

- [ ] **Step 3: Commit** — `feat(ai-chat): lifespan wiring — orphan sweep + task tracking`

---

### Task 6: Full suite + CLAUDE.md + docs + merge

- [ ] **Step 1:** `uv run ruff format && uv run ruff check && uv run pyright && uv run pytest -q`. All green.

- [ ] **Step 2:** CLAUDE.md — flip 7c to ✅, Phase 8 (preview) to ⏭ next. Add locked-in decisions for the chat flow (HTMX polling, persistent sessions, independent turns, inline background task, orphan sweep).

- [ ] **Step 3:** README — add a "Chat with the generator" section with `/ai` screenshot description + the URL.

- [ ] **Step 4:** docs/index.html — roadmap: 7c ✅, add Phase 8 entry. Hero line update.

- [ ] **Step 5:** docs/architecture.md — add "AI chat surface (Phase 7c)" section with the URL map, polling pattern, background-task flow, orphan sweep.

- [ ] **Step 6:** Push branch, `gh pr create`, `gh pr merge --squash`.
