"""Live-API integration test for the rewritten system prompt.

Skipped by default. To run:

    ANTHROPIC_API_KEY=sk-... uv run pytest \\
        packages/parcel-shell/tests/test_ai_prompt_live_generation.py -v

Costs real Anthropic-API tokens (~30s, ~$0.05). The test asserts the
shape of the generated module — that the discipline rules in the prompt
actually steered the model to:
  - always emit seed.py (Phase 11 follow-up closure),
  - emit dashboards when the user prompt asks for one,
  - emit a workflow with SendEmail + the network capability when asked,
  - never declare filesystem/process/raw_sql.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

skip_reason = (
    "needs ANTHROPIC_API_KEY and PARCEL_AI_PROVIDER=api; "
    "intentionally not in CI (real tokens, slow)"
)
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason=skip_reason,
)


@pytest.mark.asyncio
async def test_generated_module_uses_features_when_asked(committing_admin) -> None:
    """End-to-end: the user prompt mentions a dashboard and an email
    workflow; the generated module had better include both."""
    from parcel_shell.ai.generator import GenerationFailure, generate_module
    from parcel_shell.ai.provider import AnthropicAPIProvider
    from parcel_shell.app import create_app
    from parcel_shell.config import get_settings
    from parcel_shell.db import sessionmaker
    from parcel_shell.sandbox.models import SandboxInstall

    settings = get_settings()
    app = create_app()
    provider = AnthropicAPIProvider(api_key=os.environ["ANTHROPIC_API_KEY"])

    async with sessionmaker()() as db:
        result = await generate_module(
            "Sales-leads CRM. I want a dashboard showing leads by stage. "
            "Send me an email at owner@example.com when a new lead is created.",
            provider=provider,
            db=db,
            app=app,
            settings=settings,
        )

    assert not isinstance(result, GenerationFailure), f"generation failed: {result}"
    assert isinstance(result, SandboxInstall)

    root = Path(result.module_root)
    by_path = {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    init_paths = [p for p in by_path if p.endswith("__init__.py") and "parcel_mod_" in p]
    assert init_paths, "no parcel_mod_*/__init__.py emitted"
    init_text = by_path[init_paths[0]].read_text(encoding="utf-8")

    # Phase-11 follow-up closure: every AI module ships with seed.py.
    assert any(p.endswith("/seed.py") for p in by_path), "seed.py missing"

    # User asked for both — both should be present.
    assert "dashboards=" in init_text
    assert "workflows=" in init_text

    # SendEmail demands the network capability.
    assert 'capabilities=("network"' in init_text or "capabilities=('network'" in init_text

    # Forbidden caps must not appear, even if model went off-script.
    for forbidden in ("filesystem", "process", "raw_sql"):
        assert forbidden not in init_text, f"AI generator must never declare {forbidden!r}"
