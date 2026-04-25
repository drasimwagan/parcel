from __future__ import annotations

from datetime import UTC, datetime

from parcel_sdk import EmitAudit, OnCreate, UpdateField, Workflow, WorkflowContext


def _now(_ctx: WorkflowContext) -> datetime:
    return datetime.now(UTC)


welcome_workflow = Workflow(
    slug="new_contact_welcome",
    title="Welcome new contact",
    permission="contacts.read",
    triggers=(OnCreate("contacts.contact.created"),),
    actions=(
        UpdateField(field="welcomed_at", value=_now),
        EmitAudit(message="Welcomed {{ subject.first_name or subject.email }}"),
    ),
    description="Stamps welcomed_at and writes a friendly audit message when a contact is created.",
)
