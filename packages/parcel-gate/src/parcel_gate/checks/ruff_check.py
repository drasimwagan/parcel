"""Ruff check via subprocess.

We shell out to the ruff CLI with ``--output-format=json`` rather than using
ruff's Python API because the latter is not stable across versions. Subprocess
latency is on the order of tens of milliseconds for a typical module, which is
fine for our budget.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from parcel_gate.report import GateFinding

_RUFF_ERROR_PREFIXES = ("E", "F")  # syntax + pyflakes → hard errors


def run_ruff(module_root: Path) -> list[GateFinding]:
    """Lint every .py under ``module_root`` and return structured findings."""
    result = subprocess.run(  # noqa: S603
        [
            "ruff",
            "check",
            "--isolated",
            "--output-format=json",
            "--no-fix",
            "--select=E,F,W,B,UP,I",
            str(module_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # 0 = clean, 1 = findings. Anything else indicates ruff itself crashed.
    if result.returncode not in (0, 1):
        raise RuntimeError(f"ruff crashed (rc={result.returncode}): {result.stderr}")
    stdout = result.stdout.strip()
    if not stdout:
        return []
    raw = json.loads(stdout)
    findings: list[GateFinding] = []
    for item in raw:
        rule = item["code"]
        severity = "error" if rule[0] in _RUFF_ERROR_PREFIXES else "warning"
        findings.append(
            GateFinding(
                check="ruff",
                severity=severity,
                path=str(Path(item["filename"]).relative_to(module_root)),
                line=item["location"]["row"],
                rule=rule,
                message=item["message"],
            )
        )
    return findings
