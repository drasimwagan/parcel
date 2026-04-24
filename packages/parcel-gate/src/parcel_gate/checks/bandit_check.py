"""Bandit check, run in-process.

We instantiate ``BanditManager`` directly rather than shelling out because
bandit's Python API is stable and gives us structured issue objects.
"""

from __future__ import annotations

from pathlib import Path

from bandit.core import config as b_config
from bandit.core import manager as b_manager

from parcel_gate.report import GateFinding

_SEVERITY_MAP = {"LOW": "warning", "MEDIUM": "error", "HIGH": "error"}


def run_bandit(module_root: Path) -> list[GateFinding]:
    """Scan every .py under ``module_root`` and return structured findings."""
    py_files = [str(p) for p in module_root.rglob("*.py")]
    if not py_files:
        return []
    cfg = b_config.BanditConfig()
    mgr = b_manager.BanditManager(cfg, "file")
    mgr.discover_files(py_files, recursive=False)
    mgr.run_tests()
    findings: list[GateFinding] = []
    for issue in mgr.get_issue_list():
        severity = _SEVERITY_MAP.get(getattr(issue, "severity", "LOW"), "warning")
        findings.append(
            GateFinding(
                check="bandit",
                severity=severity,  # type: ignore[arg-type]
                path=str(Path(issue.fname).relative_to(module_root)),
                line=issue.lineno,
                rule=issue.test_id,
                message=issue.text,
            )
        )
    return findings
