from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from parcel_sdk import (
    EmitAudit,
    Manual,
    OnCreate,
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
