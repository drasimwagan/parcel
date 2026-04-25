from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Module, Report


@dataclass(frozen=True)
class RegisteredReport:
    module_name: str
    report: Report


def collect_reports(app) -> list[RegisteredReport]:
    """Walk active modules' manifests and return their reports in stable order.

    Reads ``app.state.active_modules_manifest`` (populated by ``mount_module``).
    Returns ``[]`` if state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredReport] = []
    for name in sorted(manifests):
        module = manifests[name]
        for report in module.reports:
            out.append(RegisteredReport(module_name=name, report=report))
    return out


def find_report(
    registered: list[RegisteredReport], module_name: str, slug: str
) -> RegisteredReport | None:
    for r in registered:
        if r.module_name == module_name and r.report.slug == slug:
            return r
    return None
