from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.workflows.serialize import (
    _import_class,
    decode_event,
    encode_events,
)

pytestmark = pytest.mark.asyncio


def test_encode_event_with_no_subject() -> None:
    out = encode_events(
        [{"event": "x.y", "subject": None, "subject_id": None, "changed": ()}]
    )
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


async def test_decode_event_missing_row_resolves_to_none_subject(
    db_session: AsyncSession,
) -> None:
    """If the row doesn't exist, subject is None.

    Uses WorkflowAudit (a shell-level mapped class) — no contacts module
    dependency. Same code path as decoding any subject_ref against a session
    where the referenced row has been deleted.
    """
    payload = {
        "event": "x.y",
        "subject_ref": {
            "class_path": "parcel_shell.workflows.models.WorkflowAudit",
            "id": str(uuid.uuid4()),
        },
        "subject_id": str(uuid.uuid4()),
        "changed": [],
    }
    out = await decode_event(payload, db_session)
    assert out["subject"] is None
    assert out["subject_id"] is not None  # the id round-trips even without the row
