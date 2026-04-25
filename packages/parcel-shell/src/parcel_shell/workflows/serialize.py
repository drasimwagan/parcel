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
