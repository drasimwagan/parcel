"""Workspace-root conftest.

Makes the shell's test fixtures visible to all workspace tests by loading
``_shell_fixtures`` as a pytest plugin. Fixtures defined there
(``committing_admin``, ``migrations_applied``, ``patch_entry_points``, etc.)
are available to shell tests and module tests alike.

Also binds ``parcel_sdk.shell_api`` at collection start. Modules register
FastAPI deps via ``Depends(shell_api.require_permission(...))`` at import
time, so the facade must already be bound before any router module loads.
In production, ``parcel_shell.app.create_app`` binds early enough because
module discovery happens inside lifespan, after the bind call.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHELL_TESTS = Path(__file__).parent / "packages" / "parcel-shell" / "tests"
if str(_SHELL_TESTS) not in sys.path:
    sys.path.insert(0, str(_SHELL_TESTS))

pytest_plugins = ["_shell_fixtures"]


def _bind_shell_api_for_tests() -> None:
    from parcel_sdk import shell_api
    from parcel_shell.config import get_settings
    from parcel_shell.shell_api_impl import DefaultShellBinding

    shell_api.bind(DefaultShellBinding(get_settings()), force=True)


_bind_shell_api_for_tests()
