# Phase 10b — Workflows Cron + ARQ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `OnSchedule(hour=..., minute=..., ...)` triggers; route all workflow dispatch through ARQ at runtime; ship a `worker` compose service running `parcel worker`. Keep existing 10a tests green via `PARCEL_WORKFLOWS_INLINE=1` short-circuit.

**Architecture:** SDK gains an `OnSchedule` trigger (frozen, kw_only, ARQ-native kwargs). The shell's `_on_after_commit` listener splits into two paths — inline (current 10a behaviour, keyed off env var) and queued (Redis enqueue via `ArqRedis`). A new `parcel_shell.workflows.serialize` module reduces SQLAlchemy subjects to `{class_path, id}` for JSON-safe transport; the worker re-fetches via `importlib + session.get`. A new `parcel_shell.workflows.worker` module provides `build_worker_settings(settings)` — discovers active modules at boot, generates one ARQ cron job per `OnSchedule` trigger across all modules, and registers two job functions (`run_event_dispatch` for emit-driven dispatch, `run_scheduled_workflow` for cron firings). The CLI gains `parcel worker` which calls `arq.run_worker(WorkerSettings)`. Contacts ships a `daily_audit_summary` reference workflow.

**Tech Stack:** Python 3.12, ARQ 0.26+, Redis 7, SQLAlchemy 2.0 async, FastAPI, Typer, pytest-asyncio, testcontainers.

**Spec:** [`docs/superpowers/specs/2026-04-25-phase-10b-workflows-cron-arq-design.md`](../specs/2026-04-25-phase-10b-workflows-cron-arq-design.md)

**Spec deviations (resolved here):**

1. The spec sketches `app.state.arq_redis` populated in lifespan. Plan: do exactly that — `from arq import create_pool` + `await create_pool(RedisSettings.from_dsn(settings.redis_url))` inside the existing `lifespan` AsyncIterator. Stash on `session.info["arq_redis"]` from `db.get_session`, same pattern as `sessionmaker`.
2. The spec's `_discover_manifest_sync` runs `asyncio.run(...)` from within `build_worker_settings`. That's only safe when called from a non-async context (the `parcel worker` CLI). Plan: have `build_worker_settings` accept an already-discovered manifest dict, OR call a sync-only DB query helper. Choosing the latter — use `sqlalchemy.create_engine` + sync `select` for boot-time module discovery to sidestep the nested-loop concern. Documented in the worker module.
3. **Default `PARCEL_WORKFLOWS_INLINE=1` for the entire pytest suite** in `pyproject.toml`'s pytest config so existing 10a tests don't need fixture changes. The few new ARQ-integration tests explicitly unset the var via `monkeypatch.delenv`.

---

## File structure

### Created

| Path | Responsibility |
|---|---|
| `packages/parcel-shell/src/parcel_shell/workflows/serialize.py` | `encode_events`, `decode_event`, `_import_class` |
| `packages/parcel-shell/src/parcel_shell/workflows/worker.py` | `run_event_dispatch`, `run_scheduled_workflow`, `build_worker_settings`, sync module-discovery helper |
| `packages/parcel-cli/src/parcel_cli/commands/worker.py` | `parcel worker` subcommand |
| `packages/parcel-shell/tests/test_workflows_serialize.py` | Encode/decode round-trip tests |
| `packages/parcel-shell/tests/test_workflows_worker.py` | Worker-handler unit tests |
| `packages/parcel-shell/tests/test_workflows_worker_integration.py` | ARQ end-to-end via testcontainer Redis |
| `packages/parcel-cli/tests/test_cli_worker.py` | CLI subcommand smoke tests |
| `modules/contacts/tests/test_contacts_workflow_daily.py` | Reference cron workflow |

### Modified

| Path | Change |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/workflows.py` | Add `OnSchedule` dataclass with `__post_init__` validation; widen `Trigger` union |
| `packages/parcel-sdk/src/parcel_sdk/__init__.py` | Re-export `OnSchedule`; bump `__version__` to `0.7.0` |
| `packages/parcel-sdk/tests/test_workflows.py` | `OnSchedule` tests (creation, defaults, validation) |
| `packages/parcel-shell/pyproject.toml` | Add `arq>=0.26,<1.0` to runtime deps |
| `packages/parcel-shell/src/parcel_shell/app.py` | Lifespan opens `app.state.arq_redis = await create_pool(...)`, closes on shutdown |
| `packages/parcel-shell/src/parcel_shell/db.py` | Stash `arq_redis` on `session.info` from `request.app.state.arq_redis` |
| `packages/parcel-shell/src/parcel_shell/workflows/bus.py` | `_on_after_commit` splits into inline + ARQ enqueue paths |
| `packages/parcel-shell/src/parcel_shell/workflows/runner.py` | `_matches` returns False for `OnSchedule` |
| `packages/parcel-shell/tests/test_workflows_bus.py` | New cases for ARQ-enqueue path + INLINE short-circuit + missing-redis warning |
| `pyproject.toml` (workspace root) | Pytest env var `PARCEL_WORKFLOWS_INLINE=1` |
| `packages/parcel-cli/src/parcel_cli/main.py` | Register `worker` command |
| `packages/parcel-cli/src/parcel_cli/commands/dev.py` | Set `PARCEL_WORKFLOWS_INLINE=1` + print banner |
| `docker-compose.yml` | Add `worker` service |
| `modules/contacts/src/parcel_mod_contacts/workflows.py` | Add `daily_audit_summary` |
| `modules/contacts/src/parcel_mod_contacts/__init__.py` | Bump to `0.5.0`; add to manifest |
| `modules/contacts/pyproject.toml` | Bump to `0.5.0` |
| `docs/module-authoring.md` | OnSchedule + worker subsection |
| `CLAUDE.md` | Phase 10b → done; locked-decisions block; current-phase + next-phase pointer |
| `docs/index.html` | Roadmap + stat-line |

---

## Task 1: SDK — `OnSchedule` trigger

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/workflows.py`
- Modify: `packages/parcel-sdk/src/parcel_sdk/__init__.py`
- Modify: `packages/parcel-sdk/tests/test_workflows.py`

- [ ] **Step 1: Write the failing tests**

Append to `packages/parcel-sdk/tests/test_workflows.py`:

```python
from parcel_sdk import OnSchedule


def test_onschedule_defaults_all_fields_to_none() -> None:
    t = OnSchedule()
    assert t.second is None
    assert t.minute is None
    assert t.hour is None
    assert t.day is None
    assert t.month is None
    assert t.weekday is None


def test_onschedule_accepts_int_or_set() -> None:
    t1 = OnSchedule(hour=9, minute=0)
    assert t1.hour == 9
    t2 = OnSchedule(hour={9, 17}, minute=0, weekday={0, 1, 2, 3, 4})
    assert t2.hour == {9, 17}
    assert t2.weekday == {0, 1, 2, 3, 4}


def test_onschedule_is_frozen_kw_only() -> None:
    t = OnSchedule(hour=9)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.hour = 10  # type: ignore[misc]
    with pytest.raises(TypeError):
        OnSchedule(0, 0)  # type: ignore[misc] -- not kw_only


def test_onschedule_rejects_out_of_range_hour() -> None:
    with pytest.raises(ValueError, match="hour"):
        OnSchedule(hour=24)


def test_onschedule_rejects_out_of_range_minute() -> None:
    with pytest.raises(ValueError, match="minute"):
        OnSchedule(minute=60)


def test_onschedule_rejects_out_of_range_weekday() -> None:
    with pytest.raises(ValueError, match="weekday"):
        OnSchedule(weekday=7)


def test_onschedule_rejects_set_with_invalid_member() -> None:
    with pytest.raises(ValueError, match="hour"):
        OnSchedule(hour={9, 25})
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v -k onschedule
```

Expected: ImportError on `from parcel_sdk import OnSchedule`.

- [ ] **Step 3: Implement `OnSchedule`**

Edit `packages/parcel-sdk/src/parcel_sdk/workflows.py`. Add after `Manual`:

```python
_RANGES = {
    "second": (0, 59),
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),
}


@dataclass(frozen=True, kw_only=True)
class OnSchedule:
    """Fires from the worker's cron scheduler.

    Each field accepts an `int`, a `set[int]`, or `None` (matches any).
    Fields follow ARQ's `cron()` semantics:

    - `second`, `minute`: 0-59
    - `hour`: 0-23
    - `day`: 1-31
    - `month`: 1-12
    - `weekday`: 0-6 (Monday is 0; matches `datetime.weekday()`)

    Examples:
        OnSchedule(hour=9, minute=0)                       # daily at 09:00
        OnSchedule(hour=9, minute=0, weekday={0,1,2,3,4})  # weekdays at 09:00
        OnSchedule(minute={0, 15, 30, 45})                 # every 15 minutes
    """

    second: int | set[int] | None = None
    minute: int | set[int] | None = None
    hour: int | set[int] | None = None
    day: int | set[int] | None = None
    month: int | set[int] | None = None
    weekday: int | set[int] | None = None

    def __post_init__(self) -> None:
        for name, (lo, hi) in _RANGES.items():
            value = getattr(self, name)
            if value is None:
                continue
            members = value if isinstance(value, set) else {value}
            for v in members:
                if not isinstance(v, int) or v < lo or v > hi:
                    raise ValueError(
                        f"OnSchedule {name}={value!r} out of range [{lo}, {hi}]"
                    )
```

Update the `Trigger` union:

```python
Trigger = OnCreate | OnUpdate | Manual | OnSchedule
```

Update `__all__`:

```python
__all__ = [
    "Action",
    "EmitAudit",
    "Manual",
    "OnCreate",
    "OnSchedule",
    "OnUpdate",
    "Trigger",
    "UpdateField",
    "Workflow",
    "WorkflowContext",
]
```

- [ ] **Step 4: Re-export from the SDK package**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py`. Add `OnSchedule` to the workflows import block and to `__all__`. Bump `__version__` to `"0.7.0"`. Update the docstring's phase note to "Phase 10b surface: Phase 10a + OnSchedule".

- [ ] **Step 5: Run and verify pass**

```bash
uv run pytest packages/parcel-sdk/tests/test_workflows.py -v
```

Expected: 19 passed (12 from 10a + 7 new).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/workflows.py \
        packages/parcel-sdk/src/parcel_sdk/__init__.py \
        packages/parcel-sdk/tests/test_workflows.py
git commit -m "feat(sdk): add OnSchedule trigger with cron-like kwargs"
```

---

## Task 2: Shell — add ARQ dependency

**Files:**
- Modify: `packages/parcel-shell/pyproject.toml`

- [ ] **Step 1: Add ARQ to deps**

Edit `packages/parcel-shell/pyproject.toml`. Inside the `dependencies = [...]` list, append:

```toml
    "arq>=0.26,<1.0",
```

- [ ] **Step 2: Sync workspace**

```bash
uv sync --all-packages
```

Expected: `arq` and its transitive deps (`croniter`, etc.) install.

- [ ] **Step 3: Verify import**

```bash
uv run python -c "import arq; from arq import create_pool; from arq.cron import cron; print('ok', arq.VERSION)"
```

Expected: prints `ok 0.26.x`.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/pyproject.toml uv.lock
git commit -m "chore(shell): add arq runtime dep for phase 10b"
```

---

## Task 3: Make `_matches` return False for `OnSchedule`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/runner.py`
- Modify: `packages/parcel-shell/tests/test_workflows_runner.py`

- [ ] **Step 1: Add the failing test**

Append to `packages/parcel-shell/tests/test_workflows_runner.py`:

```python
def test_matches_onschedule_never_via_event() -> None:
    from parcel_sdk import OnSchedule

    assert not _matches(OnSchedule(hour=9), {"event": "anything", "changed": ()})
    assert not _matches(
        OnSchedule(hour=9, minute=0),
        {"event": "demo.thing.scheduled", "changed": ()},
    )
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_runner.py -v -k onschedule
```

Expected: AssertionError — `_matches` doesn't recognise OnSchedule (returns False by virtue of falling through, but might match in the OnUpdate / OnCreate branches accidentally — actually the existing implementation falls through and returns False, so let's see). If it already passes, the implementation just needs the explicit branch for clarity.

- [ ] **Step 3: Update `_matches` for explicit handling**

Edit `packages/parcel-shell/src/parcel_shell/workflows/runner.py`. Update `_matches`:

```python
def _matches(trigger: Any, ev: dict) -> bool:
    """Does `trigger` match event dict `ev` (`{event, subject, subject_id, changed}`)?"""
    from parcel_sdk import OnSchedule

    if isinstance(trigger, (Manual, OnSchedule)):
        return False  # Manual fires only via POST /run; OnSchedule fires only via the cron worker.
    if isinstance(trigger, OnCreate):
        return trigger.event == ev["event"]
    if isinstance(trigger, OnUpdate):
        if trigger.event != ev["event"]:
            return False
        if not trigger.when_changed:
            return True
        return any(c in trigger.when_changed for c in ev.get("changed", ()))
    return False
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_runner.py -v
```

Expected: 10 passed (9 from 10a + 1 new).

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/runner.py \
        packages/parcel-shell/tests/test_workflows_runner.py
git commit -m "feat(shell): _matches treats OnSchedule like Manual (worker-only)"
```

---

## Task 4: Default `PARCEL_WORKFLOWS_INLINE=1` for tests

**Files:**
- Modify: `pyproject.toml` (workspace root)

- [ ] **Step 1: Inspect the existing pytest config**

```bash
grep -A 20 "tool.pytest.ini_options" pyproject.toml
```

You're looking for the `[tool.pytest.ini_options]` block. There's an `env` or no env section.

- [ ] **Step 2: Add the env var**

Edit `pyproject.toml`. Inside `[tool.pytest.ini_options]`, add an `env = [...]` line if missing, or append to it:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
# ... existing config ...
env = [
    "PARCEL_WORKFLOWS_INLINE=1",
]
```

(If `env =` already exists, append `"PARCEL_WORKFLOWS_INLINE=1"` to the list.)

The `pytest-env` plugin handles this; check if it's a dev dep. If not, add to `[dependency-groups] dev`:

```toml
[dependency-groups]
dev = [
    # ... existing ...
    "pytest-env>=1.1",
]
```

(If pytest-env isn't already there.)

- [ ] **Step 3: Sync and verify**

```bash
uv sync
uv run python -c "import os; os.environ.setdefault('FORTEST', '0'); print('ok')"
```

- [ ] **Step 4: Run a quick test confirming the env var is set**

Add this temporary test to `packages/parcel-shell/tests/test_workflows_bus.py`:

```python
def test_pytest_inline_env_var_is_set() -> None:
    import os

    assert os.environ.get("PARCEL_WORKFLOWS_INLINE") == "1"
```

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py::test_pytest_inline_env_var_is_set -v
```

Expected: PASS. If FAIL, the env config didn't take — investigate (perhaps pytest-env not installed).

- [ ] **Step 5: Remove the temporary test**

Delete `test_pytest_inline_env_var_is_set` from `test_workflows_bus.py` after confirming. The behaviour is implicitly verified by every later workflow test.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "test: default PARCEL_WORKFLOWS_INLINE=1 across pytest suite"
```

---

## Task 5: Lifespan — open ArqRedis pool

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`
- Modify: `packages/parcel-shell/src/parcel_shell/db.py`

- [ ] **Step 1: Open the pool in lifespan**

Edit `packages/parcel-shell/src/parcel_shell/app.py`. Inside the `lifespan` function, just after `app.state.redis = redis_async.from_url(...)`:

```python
        from arq.connections import RedisSettings, create_pool

        app.state.arq_redis = await create_pool(
            RedisSettings.from_dsn(settings.redis_url)
        )
```

In the lifespan's `finally` block (where `await app.state.redis.aclose()` is), add:

```python
            await app.state.arq_redis.close()
```

(Put it right before the existing `await app.state.redis.aclose()` line.)

- [ ] **Step 2: Stash `arq_redis` on the session in `get_session`**

Edit `packages/parcel-shell/src/parcel_shell/db.py`. Inside `get_session`, after `session.info["sessionmaker"] = sessionmaker`:

```python
        session.info["arq_redis"] = getattr(request.app.state, "arq_redis", None)
```

- [ ] **Step 3: Run the existing app-factory test to verify lifespan still works**

```bash
uv run pytest packages/parcel-shell/tests/test_app_factory.py -v
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/app.py \
        packages/parcel-shell/src/parcel_shell/db.py
git commit -m "feat(shell): open ArqRedis pool in lifespan + stash on session.info"
```

---

## Task 6: Serializer (`encode_events` / `decode_event`)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/serialize.py`
- Create: `packages/parcel-shell/tests/test_workflows_serialize.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_workflows_serialize.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.workflows.serialize import (
    _import_class,
    decode_event,
    encode_events,
)

pytestmark = pytest.mark.asyncio


def test_encode_event_with_no_subject() -> None:
    out = encode_events([{"event": "x.y", "subject": None, "subject_id": None, "changed": ()}])
    assert out == [
        {"event": "x.y", "subject_ref": None, "subject_id": None, "changed": []}
    ]


def test_encode_event_with_subject_carries_class_path_and_id() -> None:
    sid = uuid.uuid4()

    class FakeMapped:
        pass

    inst = FakeMapped()
    inst.id = sid
    out = encode_events(
        [{"event": "x.y", "subject": inst, "subject_id": sid, "changed": ("email",)}]
    )
    assert len(out) == 1
    ref = out[0]["subject_ref"]
    assert ref is not None
    assert ref["class_path"].endswith("FakeMapped")
    assert ref["id"] == str(sid)
    assert out[0]["subject_id"] == str(sid)
    assert out[0]["changed"] == ["email"]


def test_import_class_round_trip() -> None:
    cls = _import_class("collections.OrderedDict")
    from collections import OrderedDict

    assert cls is OrderedDict


async def test_decode_event_no_subject_round_trip(db_session: AsyncSession) -> None:
    payload = {"event": "x.y", "subject_ref": None, "subject_id": None, "changed": []}
    out = await decode_event(payload, db_session)
    assert out["event"] == "x.y"
    assert out["subject"] is None
    assert out["subject_id"] is None
    assert out["changed"] == ()


async def test_decode_event_with_subject_re_fetches(contacts_session: AsyncSession) -> None:
    from parcel_mod_contacts.models import Contact

    sid = uuid.uuid4()
    contacts_session.add(Contact(id=sid, email="a@b.com", first_name="X"))
    await contacts_session.commit()

    payload = {
        "event": "contacts.contact.created",
        "subject_ref": {
            "class_path": "parcel_mod_contacts.models.Contact",
            "id": str(sid),
        },
        "subject_id": str(sid),
        "changed": [],
    }
    out = await decode_event(payload, contacts_session)
    assert out["subject"] is not None
    assert out["subject"].email == "a@b.com"
    assert out["subject_id"] == sid


async def test_decode_event_missing_row_resolves_to_none_subject(
    contacts_session: AsyncSession,
) -> None:
    """If the row was deleted between commit and decode, subject is None."""
    payload = {
        "event": "contacts.contact.created",
        "subject_ref": {
            "class_path": "parcel_mod_contacts.models.Contact",
            "id": str(uuid.uuid4()),
        },
        "subject_id": str(uuid.uuid4()),
        "changed": [],
    }
    out = await decode_event(payload, contacts_session)
    assert out["subject"] is None
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_serialize.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `serialize.py`**

`packages/parcel-shell/src/parcel_shell/workflows/serialize.py`:

```python
"""Event-payload serialization for cross-process workflow dispatch.

The shell emits events containing live SQLAlchemy model instances; ARQ jobs
serialize their args via msgpack and need JSON-safe payloads. We reduce the
subject to a `{class_path, id}` referent; the worker re-imports the class via
`importlib` and re-fetches the row in its own session.
"""

from __future__ import annotations

import importlib
from typing import Any
from uuid import UUID


def _import_class(class_path: str) -> type:
    """Resolve `module.path.ClassName` to the class object."""
    module_path, _, name = class_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, name)


def encode_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert in-memory event dicts into JSON-serializable payloads.

    Subject is reduced to `{class_path, id}` (or None). subject_id is
    stringified for portability across msgpack / JSON.
    """
    out: list[dict[str, Any]] = []
    for ev in events:
        subj = ev.get("subject")
        sid = ev.get("subject_id")
        subject_ref: dict[str, str] | None
        if subj is None:
            subject_ref = None
        else:
            cls = type(subj)
            subject_ref = {
                "class_path": f"{cls.__module__}.{cls.__qualname__}",
                "id": str(sid) if sid is not None else "",
            }
        out.append(
            {
                "event": ev["event"],
                "subject_ref": subject_ref,
                "subject_id": str(sid) if sid is not None else None,
                "changed": list(ev.get("changed", ())),
            }
        )
    return out


async def decode_event(payload: dict[str, Any], session) -> dict[str, Any]:
    """Inverse of `encode_events`. Re-fetches the subject if a ref is supplied.

    Returns a dict shaped like the in-memory event:
    `{event, subject, subject_id, changed}`. If the referenced row no longer
    exists, `subject` is None and the action chain may fail at runtime
    (audit captures it).
    """
    subj: Any = None
    subj_id: UUID | None = None
    ref = payload.get("subject_ref")
    if ref and ref.get("id"):
        cls = _import_class(ref["class_path"])
        subj_id = UUID(ref["id"])
        subj = await session.get(cls, subj_id)
    elif payload.get("subject_id"):
        subj_id = UUID(payload["subject_id"])
    return {
        "event": payload["event"],
        "subject": subj,
        "subject_id": subj_id,
        "changed": tuple(payload.get("changed", [])),
    }
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_serialize.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/serialize.py \
        packages/parcel-shell/tests/test_workflows_serialize.py
git commit -m "feat(shell): event-payload serialize for cross-process dispatch"
```

---

## Task 7: Bus — split into inline + ARQ enqueue

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/workflows/bus.py`
- Modify: `packages/parcel-shell/tests/test_workflows_bus.py`

- [ ] **Step 1: Add the failing tests**

Append to `packages/parcel-shell/tests/test_workflows_bus.py`:

```python
async def test_after_commit_enqueues_to_arq_when_not_inline(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without INLINE env var and with arq_redis on session.info,
    after_commit calls ArqRedis.enqueue_job with serialized events."""
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)

    enqueued: list[tuple[str, list[dict]]] = []

    class FakeArqRedis:
        async def enqueue_job(self, name: str, *args, **kwargs):
            enqueued.append((name, args, kwargs))
            return None

    db_session.info["arq_redis"] = FakeArqRedis()
    await _emit_to_session(db_session, "x.y.created", subject=None, changed=())

    # Trigger the after_commit listener manually by committing.
    # The session is a savepoint-wrapped session in tests; we still get
    # the after_commit fire when the explicit commit happens. But our
    # session is rolled back at teardown; we need a real commit. Use a flush
    # then drive the listener directly.
    from parcel_shell.workflows.bus import _on_after_commit

    _on_after_commit(db_session.sync_session)

    # Allow the asyncio.create_task we scheduled to run.
    await asyncio.sleep(0.01)
    assert len(enqueued) == 1
    name, args, kwargs = enqueued[0]
    assert name == "run_event_dispatch"
    payload = args[0]
    assert payload[0]["event"] == "x.y.created"


async def test_after_commit_skips_when_no_arq_redis_and_not_inline(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)
    db_session.info.pop("arq_redis", None)
    await _emit_to_session(db_session, "x.y.created", subject=None, changed=())

    from parcel_shell.workflows.bus import _on_after_commit

    _on_after_commit(db_session.sync_session)
    # No exception, queue dropped.
```

(Add `import asyncio` at the top of the file if missing.)

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py -v -k "arq"
```

Expected: failures on the new tests.

- [ ] **Step 3: Refactor `bus.py`**

Edit `packages/parcel-shell/src/parcel_shell/workflows/bus.py`. Replace `_on_after_commit`:

```python
import os

from sqlalchemy import event
from sqlalchemy.orm import Session


def _on_after_commit(sync_session: Session) -> None:
    """SQLAlchemy after_commit listener — runs sync; spawns the async dispatcher.

    Two paths:
    - With PARCEL_WORKFLOWS_INLINE set, dispatch happens in-process via
      `loop.create_task(dispatch_events(...))` — the Phase 10a behaviour.
    - Otherwise, the events are encoded and enqueued to Redis as an ARQ job;
      a worker process consumes the queue and runs `dispatch_events` there.
    """
    events = sync_session.info.pop("pending_events", None)
    if not events:
        return
    sessionmaker = sync_session.info.get("sessionmaker")
    if sessionmaker is None:
        _log.debug("workflows.dispatch_skipped.no_sessionmaker", event_count=len(events))
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _log.debug("workflows.dispatch_skipped.no_loop", event_count=len(events))
        return

    if os.environ.get("PARCEL_WORKFLOWS_INLINE"):
        from parcel_shell.workflows.runner import dispatch_events

        loop.create_task(dispatch_events(events, sessionmaker))
        return

    arq_redis = sync_session.info.get("arq_redis")
    if arq_redis is None:
        _log.warning("workflows.dispatch_skipped.no_arq_redis", event_count=len(events))
        return

    from parcel_shell.workflows.serialize import encode_events

    payload = encode_events(events)
    loop.create_task(arq_redis.enqueue_job("run_event_dispatch", payload))
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py -v
```

Expected: 6 passed (4 from 10a + 2 new).

- [ ] **Step 5: Run all workflow tests to confirm 10a still green**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_bus.py \
              packages/parcel-shell/tests/test_workflows_runner.py \
              packages/parcel-shell/tests/test_workflows_routes.py -v
```

Expected: all green (the inline pytest env keeps existing 10a flow).

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/bus.py \
        packages/parcel-shell/tests/test_workflows_bus.py
git commit -m "feat(shell): bus splits into ARQ enqueue + INLINE short-circuit"
```

---

## Task 8: Worker — handler functions + settings

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/workflows/worker.py`
- Create: `packages/parcel-shell/tests/test_workflows_worker.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_workflows_worker.py`:

```python
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk import EmitAudit, Module, OnCreate, OnSchedule, Workflow
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.worker import (
    _build_cron_jobs,
    run_event_dispatch,
    run_scheduled_workflow,
)

pytestmark = pytest.mark.asyncio


# ---- _build_cron_jobs ------------------------------------------------------


def test_build_cron_jobs_emits_one_per_onschedule_trigger() -> None:
    wf_a = Workflow(
        slug="daily",
        title="Daily",
        permission="x.read",
        triggers=(OnSchedule(hour=9, minute=0),),
        actions=(EmitAudit("hi"),),
    )
    wf_b = Workflow(
        slug="hourly",
        title="Hourly",
        permission="x.read",
        triggers=(OnSchedule(minute={0, 30}),),
        actions=(EmitAudit("ok"),),
    )
    manifest = {
        "demo": Module(name="demo", version="0.1.0", workflows=(wf_a, wf_b))
    }
    jobs = _build_cron_jobs(manifest)
    assert len(jobs) == 2
    # ARQ's CronJob has a `name` attribute we can read.
    names = {j.name for j in jobs}
    assert names == {"demo.daily", "demo.hourly"}


def test_build_cron_jobs_skips_non_onschedule_triggers() -> None:
    wf = Workflow(
        slug="welcome",
        title="W",
        permission="x.read",
        triggers=(OnCreate("x.y.created"),),
        actions=(EmitAudit("hi"),),
    )
    manifest = {"demo": Module(name="demo", version="0.1.0", workflows=(wf,))}
    assert _build_cron_jobs(manifest) == []


# ---- run_event_dispatch ----------------------------------------------------


async def test_run_event_dispatch_decodes_payload_and_writes_audit(
    sessionmaker_factory, monkeypatch
) -> None:
    """A serialized event payload runs through dispatch + writes an audit row."""
    from types import SimpleNamespace

    wf = Workflow(
        slug="cap",
        title="C",
        permission="x.read",
        triggers=(OnCreate("a"),),
        actions=(EmitAudit("ran for {{ event }}"),),
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={"demo": Module(name="demo", version="0.1.0", workflows=(wf,))}
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    payload = [
        {
            "event": "a",
            "subject_ref": None,
            "subject_id": None,
            "changed": [],
        }
    ]
    ctx = {"sessionmaker": sessionmaker_factory}
    await run_event_dispatch(ctx, payload)

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].workflow_slug == "cap"
        assert rows[0].status == "ok"


# ---- run_scheduled_workflow ------------------------------------------------


async def test_run_scheduled_workflow_writes_synthetic_event_audit(
    sessionmaker_factory, monkeypatch
) -> None:
    from types import SimpleNamespace

    wf = Workflow(
        slug="daily",
        title="D",
        permission="x.read",
        triggers=(OnSchedule(hour=9, minute=0),),
        actions=(EmitAudit("Daily {{ event }}"),),
    )
    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={"demo": Module(name="demo", version="0.1.0", workflows=(wf,))}
        )
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    ctx = {"sessionmaker": sessionmaker_factory, "app": fake_app}
    await run_scheduled_workflow(ctx, "demo", "daily")

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].event == "demo.daily.scheduled"
        assert rows[0].subject_id is None
        assert rows[0].status == "ok"
        assert "demo.daily.scheduled" in rows[0].payload.get("audit_message", "")


async def test_run_scheduled_workflow_unknown_slug_is_noop(sessionmaker_factory) -> None:
    from types import SimpleNamespace

    fake_app = SimpleNamespace(
        state=SimpleNamespace(active_modules_manifest={})
    )
    from parcel_shell.workflows import runner

    runner._active_app = fake_app

    ctx = {"sessionmaker": sessionmaker_factory, "app": fake_app}
    await run_scheduled_workflow(ctx, "nope", "none")

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert rows == []
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement worker**

`packages/parcel-shell/src/parcel_shell/workflows/worker.py`:

```python
"""ARQ worker entry points for workflow dispatch + cron firing.

Two job functions are registered with ARQ:
- `run_event_dispatch(ctx, payload)` — processes a list of emit-driven events
  enqueued by `_on_after_commit`.
- `run_scheduled_workflow(ctx, module_name, slug)` — fired by ARQ's cron
  scheduler; constructs a synthetic event with `subject=None`.

The CLI command `parcel worker` calls `arq.run_worker` against the class
returned by :func:`build_worker_settings`. That function discovers active
modules synchronously at boot to populate `cron_jobs`; restart the worker
to pick up newly-installed `OnSchedule` workflows.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import structlog
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from parcel_sdk import OnSchedule
from parcel_shell.config import Settings, get_settings
from parcel_shell.workflows.registry import collect_workflows, find_workflow
from parcel_shell.workflows.runner import dispatch_events, run_workflow, set_active_app
from parcel_shell.workflows.serialize import decode_event

_log = structlog.get_logger("parcel_shell.workflows.worker")


# ---- ARQ-registered job functions ------------------------------------------


async def run_event_dispatch(ctx: dict, payload: list[dict[str, Any]]) -> None:
    """Re-fetch subjects, then run dispatch_events.

    `ctx` is ARQ's per-job context; `ctx["sessionmaker"]` is set by
    :func:`_startup`.
    """
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        events = [await decode_event(p, session) for p in payload]
    await dispatch_events(events, sessionmaker)


async def run_scheduled_workflow(ctx: dict, module_name: str, slug: str) -> None:
    """Cron-fired workflow run.

    Builds a synthetic event with `subject=None`; delegates to
    :func:`run_workflow` which writes the audit row.
    """
    sessionmaker = ctx["sessionmaker"]
    fake_app = ctx["app"]
    registered = collect_workflows(fake_app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None:
        _log.warning(
            "workflows.scheduled.unknown", module=module_name, slug=slug
        )
        return
    ev = {
        "event": f"{module_name}.{slug}.scheduled",
        "subject": None,
        "subject_id": None,
        "changed": (),
    }
    await run_workflow(module_name, hit.workflow, ev, sessionmaker)


# ---- Lifecycle hooks -------------------------------------------------------


async def _startup(ctx: dict) -> None:
    """ARQ on_startup hook. Creates engine + session factory; mirrors shell
    module discovery into a SimpleNamespace 'fake app'."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx["engine"] = engine
    ctx["sessionmaker"] = sessionmaker

    manifest = await _discover_active_manifest_async(settings)
    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    ctx["app"] = fake_app
    set_active_app(fake_app)
    _log.info("workflows.worker.started", module_count=len(manifest))


async def _shutdown(ctx: dict) -> None:
    await ctx["engine"].dispose()


# ---- Discovery -------------------------------------------------------------


def _discover_active_manifest_sync(settings: Settings) -> dict[str, Any]:
    """Sync DB query for `InstalledModule.is_active=true`; used by build_worker_settings.

    Uses a sync engine so it doesn't need an outer event loop.
    """
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    discovered = {d.module.name: d for d in discover_modules()}
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(InstalledModule).where(InstalledModule.is_active.is_(True))
            ).all()
    finally:
        engine.dispose()
    manifest: dict[str, Any] = {}
    for row in rows:
        d = discovered.get(row.name)
        if d is not None:
            manifest[row.name] = d.module
    return manifest


async def _discover_active_manifest_async(settings: Settings) -> dict[str, Any]:
    """Async equivalent for use inside `_startup` (which already has a loop)."""
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    discovered = {d.module.name: d for d in discover_modules()}
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    select(InstalledModule).where(InstalledModule.is_active.is_(True))
                )
            ).all()
    finally:
        await engine.dispose()
    manifest: dict[str, Any] = {}
    for row in rows:
        d = discovered.get(row.name)
        if d is not None:
            manifest[row.name] = d.module
    return manifest


# ---- Cron-jobs builder -----------------------------------------------------


def _build_cron_jobs(manifest: dict[str, Any]) -> list:
    """One ARQ CronJob per OnSchedule trigger across all modules.

    Public API: callers pass in a dict[name, Module]; we return the CronJob
    list ARQ expects on `WorkerSettings.cron_jobs`.
    """
    jobs = []
    for module_name in sorted(manifest):
        module = manifest[module_name]
        for wf in module.workflows:
            for trigger in wf.triggers:
                if isinstance(trigger, OnSchedule):
                    jobs.append(
                        cron(
                            run_scheduled_workflow,
                            name=f"{module_name}.{wf.slug}",
                            second=trigger.second,
                            minute=trigger.minute,
                            hour=trigger.hour,
                            day=trigger.day,
                            month=trigger.month,
                            weekday=trigger.weekday,
                            kwargs={"module_name": module_name, "slug": wf.slug},
                        )
                    )
    return jobs


# ---- WorkerSettings builder (called by `parcel worker`) --------------------


def build_worker_settings(settings: Settings) -> type:
    """Return a WorkerSettings class for `arq.run_worker`.

    Discovers active modules synchronously at boot; generates one cron_jobs
    entry per OnSchedule trigger across all installed modules. Restart the
    worker to pick up newly-installed schedules.
    """
    manifest = _discover_active_manifest_sync(settings)
    jobs = _build_cron_jobs(manifest)

    class WorkerSettings:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        functions = [run_event_dispatch, run_scheduled_workflow]
        cron_jobs = jobs
        on_startup = _startup
        on_shutdown = _shutdown

    return WorkerSettings
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/workflows/worker.py \
        packages/parcel-shell/tests/test_workflows_worker.py
git commit -m "feat(shell): ARQ worker — run_event_dispatch + run_scheduled_workflow"
```

---

## Task 9: CLI — `parcel worker` subcommand

**Files:**
- Create: `packages/parcel-cli/src/parcel_cli/commands/worker.py`
- Modify: `packages/parcel-cli/src/parcel_cli/main.py`
- Create: `packages/parcel-cli/tests/test_cli_worker.py`

- [ ] **Step 1: Write the failing test**

`packages/parcel-cli/tests/test_cli_worker.py`:

```python
from __future__ import annotations

from typer.testing import CliRunner

from parcel_cli.main import app

runner = CliRunner()


def test_worker_command_help_renders() -> None:
    r = runner.invoke(app, ["worker", "--help"])
    assert r.exit_code == 0
    assert "worker" in r.output.lower()


def test_worker_command_invokes_arq_run_worker(monkeypatch) -> None:
    """Invoking `parcel worker` calls arq.run_worker with WorkerSettings."""
    captured: dict = {}

    def fake_run_worker(settings_cls, **kwargs):
        captured["settings_cls"] = settings_cls
        return None

    def fake_build(_settings):
        class FakeSettings:
            functions = []
            cron_jobs = []

        return FakeSettings

    monkeypatch.setattr("arq.run_worker", fake_run_worker)
    monkeypatch.setattr(
        "parcel_shell.workflows.worker.build_worker_settings",
        fake_build,
    )
    r = runner.invoke(app, ["worker"])
    assert r.exit_code == 0
    assert captured.get("settings_cls") is not None
    assert hasattr(captured["settings_cls"], "functions")
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-cli/tests/test_cli_worker.py -v
```

Expected: command not found / fails to parse.

- [ ] **Step 3: Implement the command**

`packages/parcel-cli/src/parcel_cli/commands/worker.py`:

```python
from __future__ import annotations


def worker() -> None:
    """Run the workflow worker (ARQ)."""
    from arq import run_worker
    from parcel_shell.config import get_settings
    from parcel_shell.workflows.worker import build_worker_settings

    settings = get_settings()
    WorkerSettings = build_worker_settings(settings)
    run_worker(WorkerSettings)
```

- [ ] **Step 4: Register the command**

Edit `packages/parcel-cli/src/parcel_cli/main.py`:

```python
from parcel_cli.commands import ai, dev, install, migrate, new_module, sandbox, serve, worker

# ... existing app declaration ...

app.command(name="worker")(worker.worker)
```

- [ ] **Step 5: Run and verify pass**

```bash
uv run pytest packages/parcel-cli/tests/test_cli_worker.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Smoke `parcel --help`**

```bash
uv run parcel --help
```

Expected: output lists `worker` alongside `dev`, `serve`, `migrate`, etc.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-cli/src/parcel_cli/commands/worker.py \
        packages/parcel-cli/src/parcel_cli/main.py \
        packages/parcel-cli/tests/test_cli_worker.py
git commit -m "feat(cli): add 'parcel worker' subcommand"
```

---

## Task 10: `parcel dev` sets `PARCEL_WORKFLOWS_INLINE=1`

**Files:**
- Modify: `packages/parcel-cli/src/parcel_cli/commands/dev.py`

- [ ] **Step 1: Update `dev.py`**

```python
from __future__ import annotations

import os

import typer
import uvicorn


def dev(
    host: str = typer.Option("0.0.0.0", "--host"),  # noqa: S104
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(True, "--reload/--no-reload"),
) -> None:
    """Run the shell with hot-reload (development).

    Sets PARCEL_WORKFLOWS_INLINE=1 so workflows fire in-process without
    needing the worker. Cron triggers won't fire under inline mode — start
    `parcel worker` separately if you need scheduled workflows.
    """
    os.environ.setdefault("PARCEL_ENV", "dev")
    os.environ["PARCEL_WORKFLOWS_INLINE"] = "1"
    typer.echo(
        "workflows running inline (sync triggers); cron triggers off — "
        "start `parcel worker` for scheduled workflows."
    )
    uvicorn.run(
        "parcel_shell.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
```

- [ ] **Step 2: Smoke**

```bash
uv run parcel dev --help
```

Expected: prints help, mentions inline mode.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-cli/src/parcel_cli/commands/dev.py
git commit -m "feat(cli): parcel dev forces inline-mode workflows + prints banner"
```

---

## Task 11: docker-compose worker service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add the service**

Edit `docker-compose.yml`. Replace the `# --- Phase 7 will add ---` comment block with:

```yaml
  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: parcel-worker
    restart: unless-stopped
    command: ["parcel", "worker"]
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - path: .env
        required: false
    volumes:
      - ./packages:/app/packages
      - ./modules:/app/modules
```

- [ ] **Step 2: Validate compose**

```bash
docker compose config 2>&1 | tail -10
```

Expected: parses without error; `worker` service appears.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): add worker service for phase 10b"
```

---

## Task 12: Worker integration test (end-to-end ARQ)

**Files:**
- Create: `packages/parcel-shell/tests/test_workflows_worker_integration.py`

- [ ] **Step 1: Inspect existing redis fixture**

```bash
grep -n "redis\|Redis" packages/parcel-shell/tests/_shell_fixtures.py | head -10
```

If there's no Redis fixture, we'll create one inline using testcontainers' Redis container.

- [ ] **Step 2: Write the integration test**

`packages/parcel-shell/tests/test_workflows_worker_integration.py`:

```python
"""End-to-end ARQ worker test.

Spins up testcontainer Redis, registers ARQ functions, enqueues a job,
runs the worker for ~3 seconds, asserts the audit row appears.
"""

from __future__ import annotations

import asyncio
from typing import Iterator

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select, text

from parcel_sdk import EmitAudit, Module, OnCreate, Workflow
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.serialize import encode_events

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def redis_container() -> Iterator[str]:
    """Start a testcontainer Redis; yield the connection URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"


async def test_worker_round_trip_event_dispatch(
    redis_container: str, sessionmaker_factory, monkeypatch
) -> None:
    monkeypatch.delenv("PARCEL_WORKFLOWS_INLINE", raising=False)

    # Build a fake app with one workflow.
    from types import SimpleNamespace

    wf = Workflow(
        slug="cap",
        title="C",
        permission="x.read",
        triggers=(OnCreate("integration.test.fired"),),
        actions=(EmitAudit("captured"),),
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

    # Enqueue a job.
    redis_settings = RedisSettings.from_dsn(redis_container)
    pool = await create_pool(redis_settings)
    try:
        payload = encode_events(
            [
                {
                    "event": "integration.test.fired",
                    "subject": None,
                    "subject_id": None,
                    "changed": (),
                }
            ]
        )
        await pool.enqueue_job("run_event_dispatch", payload)
    finally:
        await pool.close()

    # Run the worker briefly.
    from arq import Worker
    from parcel_shell.workflows.worker import (
        _shutdown,
        _startup,
        run_event_dispatch,
        run_scheduled_workflow,
    )

    # Override _startup to use our test sessionmaker_factory rather than
    # building its own engine; we need the same DB the audit query reads.
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
        burst=True,  # process all queued jobs then exit
        max_jobs=1,
    )
    try:
        await asyncio.wait_for(worker.async_run(), timeout=10.0)
    finally:
        await worker.close()

    # Audit row should be present.
    async with sessionmaker_factory() as s:
        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].workflow_slug == "cap"
        assert rows[0].status == "ok"
```

- [ ] **Step 3: Run the integration test**

```bash
uv run pytest packages/parcel-shell/tests/test_workflows_worker_integration.py -v
```

Expected: 1 passed (~10-15s including container startup).

If the Redis testcontainer dep is missing, install it:

```bash
uv add --dev testcontainers[redis]
```

Then re-run.

- [ ] **Step 4: Commit**

```bash
git add packages/parcel-shell/tests/test_workflows_worker_integration.py uv.lock
git commit -m "test(shell): worker integration round-trip via testcontainer redis"
```

---

## Task 13: Contacts — `daily_audit_summary` reference workflow

**Files:**
- Modify: `modules/contacts/src/parcel_mod_contacts/workflows.py`
- Modify: `modules/contacts/src/parcel_mod_contacts/__init__.py`
- Modify: `modules/contacts/pyproject.toml`
- Create: `modules/contacts/tests/test_contacts_workflow_daily.py`

- [ ] **Step 1: Add the workflow declaration**

Append to `modules/contacts/src/parcel_mod_contacts/workflows.py`:

```python
from parcel_sdk import OnSchedule

daily_audit_summary = Workflow(
    slug="daily_audit_summary",
    title="Daily contacts summary",
    permission="contacts.read",
    triggers=(OnSchedule(hour=9, minute=0),),
    actions=(EmitAudit(message="Daily contacts summary at {{ event }}"),),
    description="Writes a daily audit row at 09:00. Reference for OnSchedule.",
)
```

(Make sure `EmitAudit` and `Workflow` imports are already present.)

- [ ] **Step 2: Wire into the manifest + bump version**

Edit `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
from parcel_mod_contacts.workflows import daily_audit_summary, welcome_workflow
```

In the `Module(...)` call:

```python
    version="0.5.0",
    ...
    workflows=(welcome_workflow, daily_audit_summary),
```

Edit `modules/contacts/pyproject.toml`: bump `version = "0.4.0"` → `version = "0.5.0"`.

- [ ] **Step 3: Write the integration test**

`modules/contacts/tests/test_contacts_workflow_daily.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import select

from parcel_mod_contacts import module as contacts_module
from parcel_mod_contacts.workflows import daily_audit_summary
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.worker import run_scheduled_workflow

pytestmark = pytest.mark.asyncio


def test_daily_audit_summary_in_manifest() -> None:
    slugs = {wf.slug for wf in contacts_module.workflows}
    assert "daily_audit_summary" in slugs
    assert daily_audit_summary in contacts_module.workflows


async def test_run_scheduled_workflow_writes_daily_audit_row(
    sessionmaker_factory, monkeypatch
) -> None:
    """Calling the worker handler directly with ('contacts', 'daily_audit_summary')
    writes an audit row with the synthetic event name and rendered message."""
    from types import SimpleNamespace

    fake_app = SimpleNamespace(
        state=SimpleNamespace(active_modules_manifest={"contacts": contacts_module})
    )
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    ctx = {"sessionmaker": sessionmaker_factory, "app": fake_app}
    await run_scheduled_workflow(ctx, "contacts", "daily_audit_summary")

    async with sessionmaker_factory() as s:
        rows = (
            await s.scalars(
                select(WorkflowAudit).where(
                    WorkflowAudit.workflow_slug == "daily_audit_summary"
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].event == "contacts.daily_audit_summary.scheduled"
        assert rows[0].subject_id is None
        assert rows[0].status == "ok"
        assert "contacts.daily_audit_summary.scheduled" in rows[0].payload.get(
            "audit_message", ""
        )
```

- [ ] **Step 4: Run the contacts tests**

```bash
uv run pytest modules/contacts/tests/test_contacts_workflow_daily.py -v
uv run pytest modules/contacts/tests/ -q
```

Expected: 2 new passed; no regressions in existing 31 contacts tests.

- [ ] **Step 5: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/workflows.py \
        modules/contacts/src/parcel_mod_contacts/__init__.py \
        modules/contacts/pyproject.toml \
        modules/contacts/tests/test_contacts_workflow_daily.py
git commit -m "feat(contacts): ship daily_audit_summary cron workflow + bump to 0.5.0"
```

---

## Task 14: Documentation

**Files:**
- Modify: `docs/module-authoring.md`
- Modify: `CLAUDE.md`
- Modify: `docs/index.html`

- [ ] **Step 1: Update `module-authoring.md`**

Find the "Workflows (Phase 10a)" section. Inside the "Triggers" subsection, add `OnSchedule` to the table:

```markdown
| `OnSchedule(hour=, minute=, ...)` | The worker's cron loop fires it at the specified time. ARQ-native kwargs (each accepts `int`, `set[int]`, or `None`). Subject is always `None`; combine only with `EmitAudit` in 10b — `UpdateField` will fail at runtime since there's no row to update. |
```

After the existing "Wiring `emit`" section, add a new subsection:

````markdown
### Cron and the worker

`OnSchedule` triggers fire from a separate `worker` process, not from the
shell. Run it alongside the shell:

```bash
docker compose up -d worker     # production / docker dev
parcel worker                   # bare-metal dev
```

The worker discovers active modules **at boot**: install a new module
declaring an `OnSchedule` trigger and the worker won't pick it up until
restarted. (The shell mounts new modules immediately; only cron
schedules need the restart.) Plan: `parcel install ./your-module && docker
compose restart worker`.

`parcel dev` sets `PARCEL_WORKFLOWS_INLINE=1` so sync triggers fire in the
shell process — but cron triggers don't fire in inline mode. Run the worker
container if you need to test cron locally.

#### Supported `OnSchedule` kwargs

| kwarg | range | meaning |
|---|---|---|
| `second` | 0-59 | second of minute |
| `minute` | 0-59 | minute of hour |
| `hour` | 0-23 | hour of day |
| `day` | 1-31 | day of month |
| `month` | 1-12 | month |
| `weekday` | 0-6 | Monday=0, Sunday=6 |

Each accepts `int`, `set[int]`, or `None` (any).

#### Examples

```python
OnSchedule(hour=9, minute=0)                       # daily at 09:00
OnSchedule(hour=9, minute=0, weekday={0,1,2,3,4})  # weekdays at 09:00
OnSchedule(minute={0, 15, 30, 45})                 # every 15 minutes
```
````

- [ ] **Step 2: Update `CLAUDE.md`**

Replace the Phase 10a-only "Current phase" paragraph (the long one starting "Phase 10a — Workflows (engine + sync triggers) done") with a Phase-10b version. The pattern matches what we did for 10a:

```markdown
**Phase 10b — Workflows scheduled triggers + ARQ done.** Workflows now route through ARQ at runtime: `_on_after_commit` enqueues an event-dispatch job to Redis instead of `asyncio.create_task`. A new `worker` compose service (same image as the shell, `command: ["parcel", "worker"]`) consumes the queue, runs sync-trigger workflows in a fresh session, and runs cron-fired workflows on its own scheduler. New trigger `OnSchedule(hour=, minute=, second=, day=, month=, weekday=)` uses ARQ-native kwargs (`int`, `set[int]`, or `None`); subject is always `None` for cron firings. `_matches` returns `False` for `OnSchedule` (mirrors `Manual`); cron jobs invoke `run_scheduled_workflow` directly with a synthetic `<module>.<slug>.scheduled` event name. Worker discovers active modules synchronously at boot via a sync DB query — restart required on new module install (documented limitation). `PARCEL_WORKFLOWS_INLINE=1` env var (set by pytest config + by `parcel dev`) short-circuits the bus to today's `loop.create_task(dispatch_events(...))` for tests/dev; cron triggers don't fire in inline mode. Subject serialization: SQLAlchemy instances reduced to `{class_path, id}`; worker re-imports the class via `importlib` and re-fetches the row — if the row's been deleted, the action raises and audit captures the error. SDK bumped to `0.7.0` (adds `OnSchedule`); Contacts bumped to `0.5.0` and ships a reference `daily_audit_summary` workflow at 09:00. Test count: 392 → ~417.

Next: **Phase 10b-retry** (per-workflow `max_retries` + exponential backoff on top of ARQ's queue) OR **Phase 10c — Workflows rich actions** (`send_email` / `call_webhook` / `run_module_function` / `generate_report` + richer audit UI). Either is a small, well-scoped session. Start a new session; prompt: "Begin Phase 10b-retry per `CLAUDE.md` roadmap." or "Begin Phase 10c per `CLAUDE.md` roadmap." The full upcoming roadmap (10b ARQ ✅ → 10b-retry → 10c → 11) is described below under "Upcoming phases".
```

In the **Locked-in decisions** table, append after the existing `Workflow *` rows:

```markdown
| Workflow `OnSchedule` trigger | Frozen kw_only SDK dataclass with `second`/`minute`/`hour`/`day`/`month`/`weekday` (each `int` / `set[int]` / `None`). Construction-time `__post_init__` range validation. Maps directly to `arq.cron.cron(...)`. No `event` field — cron audit auto-names `<module>.<slug>.scheduled`. |
| Workflow ARQ routing | Always-through-ARQ at runtime: `_on_after_commit` enqueues `run_event_dispatch` jobs to Redis. `PARCEL_WORKFLOWS_INLINE=1` short-circuits to inline `asyncio.create_task` (set by pytest config + `parcel dev` CLI). Cron triggers don't fire under inline mode. |
| Workflow worker container | Same `parcel-shell` image, separate `worker` compose service with `command: ["parcel", "worker"]`. CLI subcommand wraps `arq.run_worker(WorkerSettings)`. `WorkerSettings` is built dynamically by `build_worker_settings(settings)` which sync-queries `InstalledModule.is_active=true` for cron_jobs at boot. Restart required on new module install. |
| Workflow event serialization | `parcel_shell.workflows.serialize` encodes SQLAlchemy subjects as `{class_path, id}` for JSON-safe transport. `decode_event` re-imports the class via `importlib` and `session.get`s the row in the worker session. Missing row → subject=None; subsequent `UpdateField` action raises and audit captures the error. |
| Workflow cron + UpdateField | `OnSchedule` triggers always have `subject=None`. `UpdateField` on a cron firing raises `RuntimeError("UpdateField requires a subject_id")` and audit `status="error"`. Documented; fix in 10c via richer actions that don't require a subject. |
```

In the **Phased roadmap** table, change Phase 10b from `⏭ next` to `✅ done`, and surface the next phase:

```markdown
| 10a | ✅ done | Workflows engine + sync triggers + minimal actions + read-only UI |
| 10b | ✅ done | Workflows scheduled triggers + ARQ + worker container |
| 10b-retry | ⏭ next | Per-workflow max_retries + exponential backoff (small phase) |
| 10c |  | Workflows rich actions + richer UI |
| 11 |  | Sandbox preview enrichment — sample-record seeding, Playwright screenshots, builds on ARQ |
```

In the **Upcoming phases** section, mark 10b shipped:

```markdown
### Phase 10b — Workflows scheduled triggers + ARQ ✅ shipped

Shipped on the `phase-10b-workflows-cron` branch. See the four "Workflow *" rows added in this phase under "Locked-in decisions" for the concrete contracts. ARQ landed as first-class infrastructure: new `worker` compose service, `parcel worker` CLI, `PARCEL_WORKFLOWS_INLINE=1` test/dev short-circuit. Subject reduced to `{class_path, id}` for cross-process serialization. Worker boot path uses a sync DB query for cron_jobs (sidesteps nested-loop concerns). Contacts ships `daily_audit_summary` at 09:00.

### Phase 10b-retry — Per-workflow retry semantics

**Scope.** Add `Workflow.max_retries: int = 0` and `Workflow.retry_backoff: ...`. Threaded through `_on_after_commit` enqueue and the worker's job exec. ARQ's per-task `max_tries` and built-in retry exception bubble through. Audit table gets a `retry_index` or `attempt` column (or new `retry_of` linking column) — schema change → migration 0008. Documented in `module-authoring.md`.
```

(Remove the old Phase 10b scope section since it's now moved to "shipped".)

- [ ] **Step 3: Update the website**

Edit `docs/index.html`. Update the hero stat-line:

```html
    <div class="stat-line"><span class="dot"></span> Phases 1–9 + 10a + 10b complete: shell, auth + RBAC, modules, admin UI, Contacts, SDK + CLI, gate + sandbox, Claude generator + chat, dashboards, reports, and workflows (sync triggers, scheduled cron, ARQ worker, audit log, read-only UI). Phase 10b-retry up next; rich actions (10c) and sandbox preview enrichment (11) follow.</div>
```

Roadmap rows:

```html
      <li>
        <span class="phase-num">10a</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">Workflows engine — trigger→action chains, sync triggers, UpdateField + EmitAudit, read-only audit UI</span>
      </li>
      <li>
        <span class="phase-num">10b</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">Workflows: scheduled triggers + ARQ — OnSchedule(hour=, minute=, ...), worker container, parcel worker CLI</span>
      </li>
      <li>
        <span class="phase-num">10b-retry</span>
        <span class="phase-status next">⏭ next</span>
        <span class="phase-goal">Workflows: per-workflow max_retries + exponential backoff on top of ARQ's queue</span>
      </li>
      <li>
        <span class="phase-num">10c</span>
        <span class="phase-status pending">planned</span>
        <span class="phase-goal">Workflows: rich actions — send_email, call_webhook, run_module_function, generate_report; richer audit UI</span>
      </li>
```

Test count line:

```html
<pre><code>uv run pytest                              <span style="color: var(--fg-muted)"># 417 tests, ~150s</span></code></pre>
```

- [ ] **Step 4: Final lint + test run**

```bash
uv run ruff check
uv run ruff format
uv run pyright
uv run pytest -q
```

Expected: green; ~417 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/module-authoring.md CLAUDE.md docs/index.html
git commit -m "docs: phase 10b authoring guide + CLAUDE.md + website update"
```

---

## Task 15: Final verification

- [ ] **Step 1: Boot dev stack manually**

```bash
docker compose up -d postgres redis
docker compose up -d worker shell
docker compose logs -f worker
```

In another shell:

```bash
docker compose exec shell parcel migrate
```

Open `http://localhost:8000`, log in, navigate to `/workflows`. Confirm `Contacts: Daily contacts summary` is listed.

POST to create a contact via `/mod/contacts/`. Wait a few seconds; refresh `/workflows/contacts/new_contact_welcome` — confirm a new audit row appeared (the welcome workflow rode ARQ via the worker, not inline).

- [ ] **Step 2: Stop the stack**

```bash
docker compose down
```

- [ ] **Step 3: Push branch and open PR**

```bash
git push -u origin phase-10b-workflows-cron
gh pr create --base main --title "Phase 10b: Workflows scheduled triggers + ARQ" --body "..."
```

(Body modeled on Phase 10a PR — summary, what shipped, spec deviations, test plan.)

---

## Self-review checklist

- [x] **Spec coverage:** Every locked decision has a task — phase split (header note), routing (Task 7), cron syntax (Task 1), trigger semantics (Tasks 3, 8), subject for cron (Task 8), sync-trigger ARQ dispatch (Task 7), subject serialization (Task 6), worker container (Task 11), worker boot (Task 8), CLI (Tasks 9, 10), inline mode (Tasks 4, 7, 10), reference workflow (Task 13), SDK 0.7.0 (Task 1), Contacts 0.5.0 (Task 13).
- [x] **Placeholder scan:** No "TBD" / "implement later". Every code step shows complete code.
- [x] **Type consistency:** `OnSchedule(second, minute, hour, day, month, weekday)` matches across SDK + worker + cron-job builder. `run_event_dispatch(ctx, payload)` matches across worker module + tests + bus enqueue. `run_scheduled_workflow(ctx, module_name, slug)` matches across worker + cron jobs + tests + contacts integration.
- [x] **Spec deviations:** flagged at top — sync DB query for `_discover_active_manifest_sync` (sidesteps nested-loop), pytest env var default, lifespan ArqRedis pool location.

---

**Plan complete. Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.
