from __future__ import annotations

from pathlib import Path

import pytest

from parcel_gate import GateError, run_gate

FIX = Path(__file__).parent / "fixtures"


def test_clean_passes_end_to_end() -> None:
    report = run_gate(FIX / "clean", declared_capabilities=frozenset())
    assert report.passed is True
    assert report.errors == ()


def test_dirty_os_fails_end_to_end() -> None:
    report = run_gate(FIX / "dirty_ast_os", declared_capabilities=frozenset())
    assert report.passed is False
    assert any(f.rule == "ast.blocked_import.os" for f in report.errors)


def test_missing_module_root_raises_gate_error() -> None:
    with pytest.raises(GateError):
        run_gate(FIX / "does_not_exist", declared_capabilities=frozenset())


def test_raw_sql_capability_unlocks_gate() -> None:
    report = run_gate(
        FIX / "dirty_ast_raw_sql",
        declared_capabilities=frozenset({"raw_sql"}),
    )
    assert report.passed is True
