from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class OnCreate:
    """Fires when an event with the given name is emitted."""

    event: str


@dataclass(frozen=True)
class OnUpdate:
    """Fires on an update event, optionally filtered by which fields changed.

    `when_changed=()` matches any update event with the right name.
    `when_changed=("email",)` fires only when "email" is in the emitted
    `changed` list.
    """

    event: str
    when_changed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Manual:
    """Fires only via POST /workflows/<module>/<slug>/run.

    The `event` is the synthetic name dispatched by the manual-trigger handler;
    used for audit logging.
    """

    event: str


Trigger = OnCreate | OnUpdate | Manual


@dataclass(frozen=True)
class UpdateField:
    """Set `field` on the trigger's subject row to `value`.

    `value` is either a literal (`"sent"`, `42`, `True`) or a
    `Callable[[WorkflowContext], Any]` that returns the value at run time.
    """

    field: str
    value: Any  # literal or Callable[[WorkflowContext], Any]


@dataclass(frozen=True)
class EmitAudit:
    """Render a Jinja `message` and store it in the audit row's payload.

    The template has `subject` (the event subject) and `event` (the event
    name) in scope.
    """

    message: str


Action = UpdateField | EmitAudit


@dataclass(frozen=True, kw_only=True)
class Workflow:
    """A trigger-to-action chain attached to a module manifest."""

    slug: str
    title: str
    permission: str
    triggers: tuple[Trigger, ...]
    actions: tuple[Action, ...]
    description: str = ""


@dataclass(frozen=True)
class WorkflowContext:
    """Per-invocation context handed to action callables (e.g. `value=lambda ctx: now()`)."""

    session: AsyncSession
    event: str
    subject: Any
    subject_id: UUID | None
    changed: tuple[str, ...] = ()


__all__ = [
    "Action",
    "EmitAudit",
    "Manual",
    "OnCreate",
    "OnUpdate",
    "Trigger",
    "UpdateField",
    "Workflow",
    "WorkflowContext",
]
