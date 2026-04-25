from __future__ import annotations

from types import SimpleNamespace

from parcel_sdk import EmitAudit, Module, OnCreate, Workflow
from parcel_shell.ui.sidebar import _workflows_section


def _wf(slug: str, perm: str) -> Workflow:
    return Workflow(
        slug=slug,
        title=f"Workflow {slug}",
        permission=perm,
        triggers=(OnCreate("x.y.created"),),
        actions=(EmitAudit("hi"),),
    )


def _request(manifest: dict[str, Module]):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    )


def test_section_visible_with_permission() -> None:
    m = Module(name="demo", version="0.1.0", workflows=(_wf("a", "demo.read"),))
    section = _workflows_section(_request({"demo": m}), {"demo.read"})
    assert section is not None
    assert section.label == "Workflows"
    assert section.items[0].href == "/workflows"


def test_section_hidden_without_permission() -> None:
    m = Module(name="demo", version="0.1.0", workflows=(_wf("a", "demo.read"),))
    section = _workflows_section(_request({"demo": m}), set())
    assert section is None


def test_section_hidden_when_no_workflows() -> None:
    m = Module(name="demo", version="0.1.0")
    section = _workflows_section(_request({"demo": m}), {"demo.read"})
    assert section is None
