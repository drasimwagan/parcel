from __future__ import annotations

from types import SimpleNamespace

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
    """Calling the worker handler directly writes an audit row with the
    synthetic event name and the rendered Jinja message."""
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
                select(WorkflowAudit).where(WorkflowAudit.workflow_slug == "daily_audit_summary")
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].event == "contacts.daily_audit_summary.scheduled"
        assert rows[0].subject_id is None
        assert rows[0].status == "ok"
        assert "contacts.daily_audit_summary.scheduled" in rows[0].payload.get("audit_message", "")
