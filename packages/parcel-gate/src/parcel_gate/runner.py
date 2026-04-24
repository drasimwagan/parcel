"""Compose the three checks into a single :class:`GateReport`."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from parcel_gate.checks.ast_policy import run_ast_policy
from parcel_gate.checks.bandit_check import run_bandit
from parcel_gate.checks.ruff_check import run_ruff
from parcel_gate.report import GateReport


class GateError(RuntimeError):
    """Raised when the gate itself cannot run (missing path, internal failure)."""


def run_gate(
    module_root: Path,
    *,
    declared_capabilities: frozenset[str],
) -> GateReport:
    """Run ruff + bandit + AST policy against ``module_root`` and report."""
    if not module_root.exists() or not module_root.is_dir():
        raise GateError(f"module_root does not exist: {module_root}")

    started = time.perf_counter()
    findings = []
    try:
        findings.extend(run_ruff(module_root))
        findings.extend(run_bandit(module_root))
        findings.extend(
            run_ast_policy(module_root, declared_capabilities=declared_capabilities)
        )
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"internal gate failure: {exc}") from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    passed = not any(f.severity == "error" for f in findings)
    return GateReport(
        passed=passed,
        findings=tuple(findings),
        ran_at=datetime.now(UTC),
        duration_ms=duration_ms,
    )
