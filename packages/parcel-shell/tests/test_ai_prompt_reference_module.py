"""Extract the embedded support_tickets reference module from the system
prompt, materialise it on disk, and run the Phase-7a static-analysis gate
against it. Catches drift between the prompt's worked example and the gate.
"""

from __future__ import annotations

import importlib.resources
import re
import textwrap
from pathlib import Path

import pytest

from parcel_gate.runner import run_gate


def _prompt_text() -> str:
    return (
        importlib.resources.files("parcel_shell.ai.prompts")
        .joinpath("generate_module.md")
        .read_text(encoding="utf-8")
    )


# Each file in the reference is shown as:
#   ### `<path>`
#   <one or more blank lines / prose>
#   ```python (or toml/html/ini)
#   <body>
#   ```
#
# We pull (path, body) pairs out for every fence that follows a path heading.
_HEADING_RE = re.compile(r"^### `([^`]+)`\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)


def _extract_reference_files(text: str) -> dict[str, str]:
    """Return {relative_path: body} for the reference module.

    Only files under `src/parcel_mod_support_tickets/...` and
    `tests/test_smoke.py` (plus the top-level `pyproject.toml`) are materialised.
    Files documented as standard-shape (alembic.ini, script.py.mako) are
    skipped because the prompt declines to inline their content.
    """
    files: dict[str, str] = {}
    skip = {
        "src/parcel_mod_support_tickets/alembic.ini",
        "src/parcel_mod_support_tickets/alembic/script.py.mako",
    }
    for heading in _HEADING_RE.finditer(text):
        path = heading.group(1)
        if path in skip:
            continue
        if not (
            path.startswith("src/parcel_mod_support_tickets/")
            or path == "tests/test_smoke.py"
            or path == "pyproject.toml"
        ):
            continue
        # Find the next fence after this heading.
        rest = text[heading.end() :]
        next_heading = _HEADING_RE.search(rest)
        scope = rest[: next_heading.start()] if next_heading else rest
        fence = _FENCE_RE.search(scope)
        if fence is None:
            pytest.fail(f"reference file {path!r} has no fenced body")
        files[path] = textwrap.dedent(fence.group(1))
    return files


def test_extraction_finds_every_referenced_file() -> None:
    files = _extract_reference_files(_prompt_text())
    expected = {
        "pyproject.toml",
        "src/parcel_mod_support_tickets/__init__.py",
        "src/parcel_mod_support_tickets/models.py",
        "src/parcel_mod_support_tickets/router.py",
        "src/parcel_mod_support_tickets/seed.py",
        "src/parcel_mod_support_tickets/dashboards.py",
        "src/parcel_mod_support_tickets/reports.py",
        "src/parcel_mod_support_tickets/workflows.py",
        "src/parcel_mod_support_tickets/templates/support_tickets/index.html",
        "src/parcel_mod_support_tickets/templates/reports/monthly_volume.html",
        "src/parcel_mod_support_tickets/alembic/env.py",
        "src/parcel_mod_support_tickets/alembic/versions/0001_init.py",
        "tests/test_smoke.py",
    }
    assert expected <= files.keys(), f"missing files: {expected - files.keys()}"


def test_reference_module_passes_gate(tmp_path: Path) -> None:
    """The embedded reference must pass the same static-analysis gate that
    AI-generated modules face. Capability is `network` (the reference uses
    SendEmail). If a future gate change rejects the reference, either the
    reference or the gate is wrong — fix one of them."""
    files = _extract_reference_files(_prompt_text())
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    report = run_gate(tmp_path, declared_capabilities=frozenset({"network"}))
    errors = [f for f in report.findings if f.severity == "error"]
    assert errors == [], (
        "reference module fails the gate. errors:\n"
        + "\n".join(f"  {f.rule} @ {f.path}:{f.line} — {f.message}" for f in errors)
    )
