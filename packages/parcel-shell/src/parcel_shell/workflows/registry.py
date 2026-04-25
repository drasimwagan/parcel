from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Module, Workflow


@dataclass(frozen=True)
class RegisteredWorkflow:
    module_name: str
    workflow: Workflow


def collect_workflows(app) -> list[RegisteredWorkflow]:
    """Walk active modules' manifests and return their workflows in stable order.

    Reads ``app.state.active_modules_manifest`` (populated by ``mount_module``).
    Returns ``[]`` if state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredWorkflow] = []
    for name in sorted(manifests):
        module = manifests[name]
        for wf in module.workflows:
            out.append(RegisteredWorkflow(module_name=name, workflow=wf))
    return out


def find_workflow(
    registered: list[RegisteredWorkflow], module_name: str, slug: str
) -> RegisteredWorkflow | None:
    for r in registered:
        if r.module_name == module_name and r.workflow.slug == slug:
            return r
    return None
