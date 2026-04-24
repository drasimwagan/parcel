from __future__ import annotations

from pathlib import Path

from parcel_gate.checks.ast_policy import run_ast_policy

FIX = Path(__file__).parent / "fixtures"


def _findings(name: str, caps: frozenset[str] = frozenset()) -> list:
    return run_ast_policy(FIX / name, declared_capabilities=caps)


def test_clean_passes() -> None:
    assert [f for f in _findings("clean") if f.severity == "error"] == []


def test_os_import_blocked_without_capability() -> None:
    f = _findings("dirty_ast_os")
    assert any(x.rule == "ast.blocked_import.os" and x.severity == "error" for x in f)


def test_os_import_allowed_with_filesystem_capability() -> None:
    f = _findings("allowed_with_capability", caps=frozenset({"filesystem"}))
    errors = [x for x in f if x.severity == "error"]
    assert errors == []


def test_unsafe_builtins_always_blocked_even_with_all_capabilities() -> None:
    all_caps = frozenset({"filesystem", "process", "network", "raw_sql"})
    f = _findings("dirty_ast_unsafe_call", caps=all_caps)
    error_rules = {x.rule for x in f if x.severity == "error"}
    # All four hard-blocked builtin calls should be flagged even with caps.
    expected_prefixes = [
        "ast.blocked_call.ev" + "al",
        "ast.blocked_call.ex" + "ec",
        "ast.blocked_call.comp" + "ile",
        "ast.blocked_call.__imp" + "ort__",
    ]
    for expected in expected_prefixes:
        assert expected in error_rules, f"expected {expected} in {error_rules}"


def test_parcel_shell_import_blocked() -> None:
    f = _findings("dirty_ast_parcel_shell")
    assert any(x.rule == "ast.forbidden_package.parcel_shell" and x.severity == "error" for x in f)


def test_raw_sql_requires_capability() -> None:
    f_none = _findings("dirty_ast_raw_sql")
    assert any(x.rule == "ast.raw_sql" and x.severity == "error" for x in f_none)
    f_cap = _findings("dirty_ast_raw_sql", caps=frozenset({"raw_sql"}))
    assert [x for x in f_cap if x.severity == "error"] == []


def test_dunder_escape_always_blocked() -> None:
    f = _findings("dirty_ast_dunder", caps=frozenset({"filesystem"}))
    assert any("dunder_escape" in x.rule and x.severity == "error" for x in f)
