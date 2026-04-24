from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import Dashboard, HeadlineWidget, Module
from parcel_shell.ui.sidebar import sidebar_for


def _req_with_dashboards(modules):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        active_modules_manifest={m.name: m for m in modules},
        active_modules={m.name for m in modules},
        active_modules_sidebar={m.name: () for m in modules},
    )))


def test_no_dashboards_link_when_none_visible() -> None:
    req = _req_with_dashboards([Module(name="a", version="0.1.0")])
    result = sidebar_for(req, perms=set())
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" not in hrefs


def test_dashboards_link_appears_when_user_has_permission() -> None:
    d = Dashboard(
        name="a.o", slug="o", title="T", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="", text="x"),),
    )
    m = Module(name="a", version="0.1.0", dashboards=(d,))
    req = _req_with_dashboards([m])
    result = sidebar_for(req, perms={"a.read"})
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" in hrefs


def test_dashboards_link_hidden_when_no_matching_permission() -> None:
    d = Dashboard(
        name="a.o", slug="o", title="T", permission="a.read",
        widgets=(HeadlineWidget(id="h", title="", text="x"),),
    )
    m = Module(name="a", version="0.1.0", dashboards=(d,))
    req = _req_with_dashboards([m])
    result = sidebar_for(req, perms={"other.perm"})
    hrefs = [i.href for s in result for i in s.items]
    assert "/dashboards" not in hrefs
