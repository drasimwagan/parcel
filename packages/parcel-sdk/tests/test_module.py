from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import MetaData

from parcel_sdk import (
    Dashboard,
    EmitAudit,
    KpiWidget,
    Module,
    OnCreate,
    Permission,
    Report,
    ReportContext,
    Workflow,
)


def test_permission_is_frozen_dataclass() -> None:
    p = Permission("foo.read", "Read foo")
    assert p.name == "foo.read"
    assert p.description == "Read foo"
    with pytest.raises((AttributeError, TypeError, Exception)):  # noqa: B017
        p.name = "bar.read"  # type: ignore[misc]


def test_module_defaults() -> None:
    m = Module(name="foo", version="0.1.0")
    assert m.permissions == ()
    assert m.capabilities == ()
    assert m.alembic_ini is None
    assert m.metadata is None


def test_module_full() -> None:
    md = MetaData(schema="mod_foo")
    m = Module(
        name="foo",
        version="1.2.3",
        permissions=(Permission("foo.read", "Read"),),
        capabilities=("http_egress",),
        alembic_ini=Path("/tmp/foo/alembic.ini"),
        metadata=md,
    )
    assert m.permissions[0].name == "foo.read"
    assert m.capabilities == ("http_egress",)
    assert m.metadata is md


def test_module_is_frozen() -> None:
    m = Module(name="foo", version="0.1.0")
    with pytest.raises((AttributeError, TypeError, Exception)):  # noqa: B017
        m.version = "0.2.0"  # type: ignore[misc]


def test_module_equality_by_value() -> None:
    a = Module(name="foo", version="0.1.0", capabilities=("x",))
    b = Module(name="foo", version="0.1.0", capabilities=("x",))
    assert a == b


async def _fn(_ctx): ...


def test_module_accepts_dashboards_tuple():
    d = Dashboard(
        name="m.overview",
        slug="overview",
        title="t",
        permission="m.read",
        widgets=(KpiWidget(id="k", title="t", data=_fn),),
    )
    m = Module(name="m", version="0.1.0", dashboards=(d,))
    assert m.dashboards == (d,)


def test_module_dashboards_defaults_empty():
    m = Module(name="m", version="0.1.0")
    assert m.dashboards == ()


async def _report_data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def test_module_reports_defaults_to_empty_tuple() -> None:
    m = Module(name="demo", version="0.1.0")
    assert m.reports == ()


def test_module_reports_accepts_tuple_of_reports() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="demo.read",
        template="reports/dir.html",
        data=_report_data,
    )
    m = Module(name="demo", version="0.1.0", reports=(r,))
    assert m.reports == (r,)


def test_module_workflows_defaults_to_empty_tuple() -> None:
    m = Module(name="demo", version="0.1.0")
    assert m.workflows == ()


def test_module_workflows_accepts_tuple() -> None:
    w = Workflow(
        slug="welcome",
        title="Welcome",
        permission="demo.read",
        triggers=(OnCreate("demo.thing.created"),),
        actions=(EmitAudit("hello"),),
    )
    m = Module(name="demo", version="0.1.0", workflows=(w,))
    assert m.workflows == (w,)


async def _wf_fn(_ctx) -> str:
    return "ok"


def test_module_workflow_functions_defaults_empty() -> None:
    m = Module(name="demo", version="0.1.0")
    assert m.workflow_functions == {}


def test_module_workflow_functions_accepts_dict() -> None:
    m = Module(name="demo", version="0.1.0", workflow_functions={"audit": _wf_fn})
    assert m.workflow_functions["audit"] is _wf_fn
