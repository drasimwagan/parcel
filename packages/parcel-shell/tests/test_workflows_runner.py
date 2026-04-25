from __future__ import annotations

import uuid
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


async def test_run_workflow_writes_ok_audit_for_emit_only(sessionmaker_factory) -> None:
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


async def test_run_workflow_audits_error_on_failing_action(sessionmaker_factory) -> None:
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

    from types import SimpleNamespace

    fake_app = SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={
                "demo": Module(name="demo", version="0.1.0", workflows=(wf_match, wf_skip))
            }
        )
    )

    from parcel_shell.workflows import runner

    monkeypatch.setattr(runner, "_active_app", fake_app, raising=False)

    await dispatch_events(
        [{"event": "a", "subject": None, "subject_id": None, "changed": ()}],
        sessionmaker_factory,
    )

    async with sessionmaker_factory() as s:
        from sqlalchemy import select

        rows = (await s.scalars(select(WorkflowAudit))).all()
        assert len(rows) == 1
        assert rows[0].workflow_slug == "match"
