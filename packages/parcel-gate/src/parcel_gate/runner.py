"""Compose the three checks into a single :class:`GateReport`."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from parcel_gate.checks.ast_policy import run_ast_policy
from parcel_gate.checks.bandit_check import run_bandit
from parcel_gate.checks.ruff_check import run_ruff
from parcel_gate.report import GateFinding, GateReport

# The gate only examines runtime/library code. Tests are allowed to import
# parcel_shell directly (per the Phase 6 contract), and build artefacts aren't
# installable code.
_EXCLUDED_PATH_SEGMENTS = {
    "tests",
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "wheels",
}


def _is_excluded(path_str: str) -> bool:
    # path_str comes from a GateFinding's already-relative path.
    parts = Path(path_str).parts
    return any(seg in _EXCLUDED_PATH_SEGMENTS for seg in parts)


def _filter(findings: list[GateFinding]) -> list[GateFinding]:
    return [f for f in findings if not _is_excluded(f.path)]


class GateError(RuntimeError):
    """Raised when the gate itself cannot run (missing path, internal failure)."""


def run_gate(
    module_root: Path,
    *,
    declared_capabilities: frozenset[str],
) -> GateReport:
    """Run ruff + bandit + AST policy against ``module_root`` and report.

    Only runtime/library source is considered. Tests, caches, and virtualenvs
    are excluded because the SDK-only import constraint is a runtime rule.
    """
    if not module_root.exists() or not module_root.is_dir():
        raise GateError(f"module_root does not exist: {module_root}")

    started = time.perf_counter()
    findings: list[GateFinding] = []
    try:
        findings.extend(_filter(run_ruff(module_root)))
        findings.extend(_filter(run_bandit(module_root)))
        findings.extend(
            _filter(run_ast_policy(module_root, declared_capabilities=declared_capabilities))
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
