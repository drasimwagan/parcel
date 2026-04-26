"""RunModuleFunction action executor."""

from __future__ import annotations

from typing import Any

from parcel_sdk import RunModuleFunction, WorkflowContext


async def execute_run_module_function(
    action: RunModuleFunction, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    """Look up `action.function` on `Module.workflow_functions` and await it."""
    # Late import to avoid a cycle (runner imports actions).
    from parcel_shell.workflows.runner import _active_app

    if _active_app is None:
        raise RuntimeError("RunModuleFunction: shell not initialised")
    manifest = getattr(_active_app.state, "active_modules_manifest", {}) or {}
    module = manifest.get(action.module)
    if module is None:
        raise RuntimeError(f"RunModuleFunction: module {action.module!r} not active")
    fn = getattr(module, "workflow_functions", {}).get(action.function)
    if fn is None:
        raise RuntimeError(f"RunModuleFunction: {action.module}.{action.function} not registered")
    ret = await fn(ctx)
    payload.setdefault("function_calls", []).append(
        {
            "module": action.module,
            "function": action.function,
            "return": str(ret)[:1024],
        }
    )
