from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI

from parcel_sdk import Module, SidebarItem
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


def _app_with_state() -> FastAPI:
    app = FastAPI()
    app.state.active_modules = set()
    app.state.active_modules_sidebar = {}
    return app


def test_mount_module_adds_router_with_prefix(tmp_path: Path) -> None:
    router = APIRouter()

    @router.get("/")
    async def _root() -> dict:
        return {"hi": "from-module"}

    templates_dir = tmp_path / "tpl"
    templates_dir.mkdir()

    module = Module(
        name="demo",
        version="0.1.0",
        router=router,
        templates_dir=templates_dir,
        sidebar_items=(SidebarItem(label="Demo", href="/mod/demo/"),),
    )
    discovered = DiscoveredModule(
        module=module, distribution_name="demo", distribution_version="0.1.0"
    )

    app = _app_with_state()
    mount_module(app, discovered)

    # Router mounted at /mod/demo
    paths = [getattr(r, "path", "") for r in app.routes]
    assert any(p.startswith("/mod/demo") for p in paths)

    # Template dir registered
    import jinja2

    from parcel_shell.ui.templates import get_templates

    loader = get_templates().env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    search = []
    for sub in loader.loaders:
        if isinstance(sub, jinja2.FileSystemLoader):
            search.extend(sub.searchpath)
    assert str(templates_dir) in search

    # State updated
    assert "demo" in app.state.active_modules
    assert app.state.active_modules_sidebar["demo"] == (
        SidebarItem(label="Demo", href="/mod/demo/"),
    )


def test_mount_module_idempotent(tmp_path: Path) -> None:
    router = APIRouter()
    module = Module(name="demo2", version="0.1.0", router=router, templates_dir=tmp_path)
    discovered = DiscoveredModule(
        module=module, distribution_name="demo2", distribution_version="0.1.0"
    )
    app = _app_with_state()
    mount_module(app, discovered)
    before = len(app.routes)
    mount_module(app, discovered)
    assert len(app.routes) == before


def test_mount_module_no_router_is_noop(tmp_path: Path) -> None:
    module = Module(name="nohttp", version="0.1.0")
    discovered = DiscoveredModule(
        module=module, distribution_name="nohttp", distribution_version="0.1.0"
    )
    app = _app_with_state()
    mount_module(app, discovered)
    assert "nohttp" in app.state.active_modules
    assert app.state.active_modules_sidebar.get("nohttp", ()) == ()


def test_mount_module_records_manifest() -> None:
    from parcel_sdk import Dashboard, HeadlineWidget

    m = Module(
        name="demo_manifest",
        version="0.1.0",
        dashboards=(
            Dashboard(
                name="demo.ov",
                slug="ov",
                title="T",
                permission="demo.read",
                widgets=(HeadlineWidget(id="h", title="t", text="x"),),
            ),
        ),
    )
    discovered = DiscoveredModule(
        module=m, distribution_name="demo_manifest", distribution_version="0.1.0"
    )
    app = FastAPI()
    mount_module(app, discovered)
    assert "demo_manifest" in app.state.active_modules_manifest
    assert app.state.active_modules_manifest["demo_manifest"] is m
