from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

import pytest

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
        OnSchedule(0, 0)  # type: ignore[misc]


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


# ---- Phase 10c — rich actions ---------------------------------------------


def test_send_email_is_frozen() -> None:
    from parcel_sdk import SendEmail

    a = SendEmail(to="x@y.com", subject="hi", body="hello")
    assert a.to == "x@y.com"
    assert a._required_capability == "network"
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.to = "z@y.com"  # type: ignore[misc]


def test_call_webhook_defaults() -> None:
    from parcel_sdk import CallWebhook

    a = CallWebhook(url="https://example.com/hook")
    assert a.method == "POST"
    assert a.headers == {}
    assert a.body is None
    assert a._required_capability == "network"


def test_run_module_function_no_capability() -> None:
    from parcel_sdk import RunModuleFunction

    a = RunModuleFunction(module="contacts", function="audit_log")
    assert a._required_capability is None


def test_generate_report_no_capability() -> None:
    from parcel_sdk import GenerateReport

    a = GenerateReport(module="contacts", slug="directory")
    assert a._required_capability is None
    assert a.params == {}


def test_action_union_includes_new_types() -> None:
    from parcel_sdk import (
        Action,
        CallWebhook,
        GenerateReport,
        RunModuleFunction,
        SendEmail,
    )

    # Each should be assignable as Action.
    actions: list[Action] = [
        SendEmail(to="x@y.com", subject="s", body="b"),
        CallWebhook(url="https://example.com/h"),
        RunModuleFunction(module="m", function="f"),
        GenerateReport(module="m", slug="s"),
    ]
    assert len(actions) == 4
