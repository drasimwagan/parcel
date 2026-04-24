from __future__ import annotations

from datetime import UTC, datetime

from parcel_gate import GateFinding, GateReport


def test_finding_roundtrips() -> None:
    f = GateFinding(
        check="ast_policy",
        severity="error",
        path="src/x.py",
        line=42,
        rule="ast.blocked_import.os",
        message="import os is not allowed",
    )
    assert GateFinding.from_dict(f.to_dict()) == f


def test_report_errors_vs_warnings() -> None:
    e = GateFinding(
        check="ruff", severity="error", path="x.py", line=1, rule="E501", message="too long"
    )
    w = GateFinding(
        check="ruff",
        severity="warning",
        path="x.py",
        line=1,
        rule="W291",
        message="trailing whitespace",
    )
    r = GateReport(
        passed=False, findings=(e, w), ran_at=datetime.now(UTC), duration_ms=42
    )
    assert r.errors == (e,)
    assert r.warnings == (w,)


def test_report_roundtrips() -> None:
    finding = GateFinding(
        check="bandit",
        severity="error",
        path="a/b.py",
        line=7,
        rule="B301",
        message="unsafe deserializer",
    )
    r = GateReport(
        passed=False,
        findings=(finding,),
        ran_at=datetime(2026, 4, 23, tzinfo=UTC),
        duration_ms=100,
    )
    assert GateReport.from_dict(r.to_dict()) == r
