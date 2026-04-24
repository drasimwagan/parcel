from __future__ import annotations

from pathlib import Path

from parcel_gate.checks.ruff_check import run_ruff

FIX = Path(__file__).parent / "fixtures"


def test_clean_fixture_passes() -> None:
    findings = run_ruff(FIX / "clean")
    assert [f for f in findings if f.severity == "error"] == []


def test_dirty_fixture_reports_f401() -> None:
    findings = run_ruff(FIX / "dirty_ruff")
    rules = [f.rule for f in findings]
    assert any(r.startswith("F") for r in rules)
