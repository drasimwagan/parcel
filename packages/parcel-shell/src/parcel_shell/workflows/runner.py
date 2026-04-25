from __future__ import annotations

from typing import Any

import jinja2
import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from parcel_sdk import (
    EmitAudit,
    Manual,
    OnCreate,
    OnSchedule,
    OnUpdate,
    UpdateField,
    Workflow,
    WorkflowContext,
)
from parcel_shell.workflows.models import WorkflowAudit
from parcel_shell.workflows.registry import collect_workflows

_log = structlog.get_logger("parcel_shell.workflows.runner")
# Audit messages are stored as text in `payload.audit_message`, not rendered as HTML.
_jinja = jinja2.Environment(autoescape=False, undefined=jinja2.StrictUndefined)  # noqa: S701

# Set by `app.py` lifespan. dispatch_events reads from here to find active workflows.
_active_app: Any = None


def set_active_app(app: Any) -> None:
    """Called once at shell startup; runner uses it to discover workflows."""
    global _active_app
    _active_app = app


def _matches(trigger: Any, ev: dict) -> bool:
    """Does `trigger` match event dict `ev` (`{event, subject, subject_id, changed}`)?"""
    if isinstance(trigger, Manual | OnSchedule):
        # Manual fires only via POST /run; OnSchedule fires only from the worker's cron loop.
        return False
    if isinstance(trigger, OnCreate):
        return trigger.event == ev["event"]
    if isinstance(trigger, OnUpdate):
        if trigger.event != ev["event"]:
            return False
        if not trigger.when_changed:
            return True
        return any(c in trigger.when_changed for c in ev.get("changed", ()))
    return False


async def execute_action(action: Any, ctx: WorkflowContext, payload: dict[str, Any]) -> None:
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
        if ctx.subject is None:
            raise RuntimeError("UpdateField needs a subject of a known mapped class")
        # Re-fetch in this session — the original was attached to a different
        # (already-committed) session.
        cls = type(ctx.subject)
        attached = await ctx.session.get(cls, ctx.subject_id)
        if attached is None:
            raise RuntimeError(
                f"UpdateField target {cls.__name__}({ctx.subject_id}) no longer exists"
            )
        value = action.value(ctx) if callable(action.value) else action.value
        setattr(attached, action.field, value)
        ctx.session.add(attached)
        payload.setdefault("updates", []).append({"field": action.field, "value": repr(value)})
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
            for idx, action in enumerate(workflow.actions):  # noqa: B007 - idx used in except
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
                    _log.exception(
                        "workflows.dispatch_failure",
                        module=r.module_name,
                        slug=r.workflow.slug,
                        error=str(exc),
                    )
