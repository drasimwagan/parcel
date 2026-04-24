from __future__ import annotations

from pathlib import Path

from parcel_gate.checks.bandit_check import run_bandit

FIX = Path(__file__).parent / "fixtures"


def test_clean_fixture_passes() -> None:
    findings = run_bandit(FIX / "clean")
    assert [f for f in findings if f.severity == "error"] == []


def test_dirty_fixture_flags_hardcoded_password() -> None:
    findings = run_bandit(FIX / "dirty_bandit")
    assert any("B105" in f.rule or "B106" in f.rule for f in findings)
