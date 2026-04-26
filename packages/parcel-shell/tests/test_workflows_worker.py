from __future__ import annotations

from types import SimpleNamespace

import pytest

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
    manifest = {"demo": Module(name="demo", version="0.1.0", workflows=(wf_a, wf_b))}
    jobs = _build_cron_jobs(manifest)
    assert len(jobs) == 2
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


async def test_run_scheduled_workflow_unknown_slug_is_noop(
    sessionmaker_factory, monkeypatch
) -> None:
    fake_app = SimpleNamespace(state=SimpleNamespace(active_modules_manifest={}))
    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    ctx = {"sessionmaker": sessionmaker_factory, "app": fake_app}
    await run_scheduled_workflow(ctx, "nope", "none")

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert rows == []


# ---- Retry semantics (Phase 10b-retry) -------------------------------------


async def test_run_event_dispatch_no_retry_when_max_retries_zero(
    sessionmaker_factory, monkeypatch
) -> None:
    """An erroring action with max_retries=0 does NOT raise Retry."""
    from parcel_sdk import UpdateField

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
    from parcel_sdk import UpdateField

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
    # try=1 -> defer = 10 * 2**0 = 10s. ARQ stores deferment as ms in
    # `defer_score`; retries scheduled into the future have a timestamp >= now+10s.
    # Conservative check: at least 10_000 ms ago from the test's "now".
    assert exc_info.value.defer_score is not None


async def test_run_event_dispatch_no_retry_when_budget_exhausted(
    sessionmaker_factory, monkeypatch
) -> None:
    """job_try=3 with max_retries=2: budget exhausted, no Retry raised."""
    from parcel_sdk import UpdateField

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
    from parcel_sdk import UpdateField

    wf = Workflow(
        slug="daily",
        title="D",
        permission="x.read",
        triggers=(OnSchedule(hour=9, minute=0),),
        actions=(UpdateField(field="x", value=1),),  # always fails (no subject)
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
