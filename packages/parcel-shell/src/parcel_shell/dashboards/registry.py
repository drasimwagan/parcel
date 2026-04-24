from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Dashboard, Module


@dataclass(frozen=True)
class RegisteredDashboard:
    module_name: str
    dashboard: Dashboard


def collect_dashboards(app) -> list[RegisteredDashboard]:
    """Walk active modules' manifests and return their dashboards in order.

    Reads ``app.state.active_modules_manifest`` (populated by mount_module).
    Returns ``[]`` if the state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredDashboard] = []
    for name in sorted(manifests):
        module = manifests[name]
        for dash in module.dashboards:
            out.append(RegisteredDashboard(module_name=name, dashboard=dash))
    return out


def find_dashboard(
    registered: list[RegisteredDashboard], module_name: str, slug: str
) -> RegisteredDashboard | None:
    for r in registered:
        if r.module_name == module_name and r.dashboard.slug == slug:
            return r
    return None
