from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from pydantic import BaseModel

from parcel_sdk import Report, ReportContext


class _Params(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {"hello": "world"}


def test_report_is_frozen_kw_only_dataclass() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="contacts.read",
        template="reports/directory.html",
        data=_data,
        params=_Params,
    )
    assert dataclasses.is_dataclass(r)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.title = "changed"  # type: ignore[misc]


def test_report_requires_kw_only() -> None:
    with pytest.raises(TypeError):
        Report("dir", "Directory", "contacts.read", "reports/directory.html", _data)  # type: ignore[misc]


def test_report_params_optional_defaults_none() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="contacts.read",
        template="reports/directory.html",
        data=_data,
    )
    assert r.params is None
    assert r.form_template is None


def test_report_context_is_frozen() -> None:
    ctx = ReportContext(session=object(), user_id=uuid4(), params=None)  # type: ignore[arg-type]
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.params = _Params()  # type: ignore[misc]
