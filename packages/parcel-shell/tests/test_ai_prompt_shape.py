"""Static assertions on the AI generator's system prompt.

These are cheap regression guards. They do not exercise the live model;
they exercise the file the live model loads. If a future edit drops a
feature section by accident, these tests catch it.

The prompt is loaded the same way the live provider loads it
(``importlib.resources``) so any drift between the file on disk and
what the provider sees is caught here too.
"""

from __future__ import annotations

import importlib.resources

import pytest


def _prompt_text() -> str:
    return (
        importlib.resources.files("parcel_shell.ai.prompts")
        .joinpath("generate_module.md")
        .read_text(encoding="utf-8")
    )


def test_prompt_loads_and_is_substantial() -> None:
    """Lower bound only — Phase 12 grew the prompt to ~750 lines (~30 KiB)."""
    text = _prompt_text()
    assert len(text) > 5000


@pytest.mark.parametrize(
    "marker",
    [
        # Feature surfaces the model must know about.
        "Module.dashboards",
        "Module.workflows",
        "Module.reports",
        "Module.workflow_functions",
        "seed.py",
        "shell_api.emit",
        # Worked-reference markers.
        "support_tickets",
        "KpiWidget",
        "BarWidget",
        "OnCreate",
        "SendEmail",
        # Discipline-section markers.
        "ALWAYS include",
        "INCLUDE BY DEFAULT",
        "ONLY IF THE USER ASKS",
    ],
)
def test_prompt_documents_each_feature(marker: str) -> None:
    assert marker in _prompt_text(), f"prompt missing required marker: {marker!r}"


def test_capability_rule_is_network_only() -> None:
    """The AI generator must be told it can add network but never the others."""
    text = _prompt_text()
    # Phrasing is fixed so a permissive rewrite is a noisy regression.
    assert "network: REQUIRED if" in text
    assert "filesystem / process / raw_sql: NEVER add" in text


def test_prompt_keeps_existing_hard_rules() -> None:
    """Hard rules from Phase 7b carry forward unchanged. Failure here means a
    rewrite accidentally dropped a security-critical clause."""
    text = _prompt_text()
    for clause in [
        "Imports `sys` or `importlib`",
        "Imports anything from `parcel_shell.*`",
        "Calls `eval`, `exec`, `compile`, or `__import__`",
        "__class__",
        "__subclasses__",
    ]:
        assert clause in text, f"hard-rule clause missing: {clause!r}"
