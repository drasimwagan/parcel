from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import Dashboard, HeadlineWidget, Module
from parcel_shell.dashboards.registry import (
    RegisteredDashboard,
    collect_dashboards,
    find_dashboard,
)


def _mkmod(name: str, dashboards: tuple[Dashboard, ...] = ()) -> Module:
    return Module(name=name, version="0.1.0", dashboards=dashboards)


def _app_with_modules(*modules: Module):
    return SimpleNamespace(
        state=SimpleNamespace(
            active_modules_manifest={m.name: m for m in modules},
            active_modules={m.name for m in modules},
        )
    )


def test_collect_dashboards_from_active_modules() -> None:
    d1 = Dashboard(
        name="a.overview",
        slug="overview",
        title="A",
        permission="a.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    d2 = Dashboard(
        name="b.stats",
        slug="stats",
        title="B",
        permission="b.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    app = _app_with_modules(_mkmod("a", (d1,)), _mkmod("b", (d2,)), _mkmod("c"))
    result = collect_dashboards(app)
    assert result == [
        RegisteredDashboard(module_name="a", dashboard=d1),
        RegisteredDashboard(module_name="b", dashboard=d2),
    ]


def test_find_dashboard_by_module_and_slug() -> None:
    d = Dashboard(
        name="a.overview",
        slug="overview",
        title="A",
        permission="a.read",
        widgets=(HeadlineWidget(id="h", title="t", text="x"),),
    )
    app = _app_with_modules(_mkmod("a", (d,)))
    reg = collect_dashboards(app)
    assert find_dashboard(reg, "a", "overview") is not None
    assert find_dashboard(reg, "a", "missing") is None
    assert find_dashboard(reg, "missing", "overview") is None


def test_collect_returns_empty_when_state_missing() -> None:
    app = SimpleNamespace(state=SimpleNamespace())
    assert collect_dashboards(app) == []
