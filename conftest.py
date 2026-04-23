"""Workspace-root conftest.

Makes the shell's test fixtures visible to all workspace tests by loading
``_shell_fixtures`` as a pytest plugin. Fixtures defined there
(``committing_admin``, ``migrations_applied``, ``patch_entry_points``, etc.)
are available to shell tests and module tests alike.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHELL_TESTS = Path(__file__).parent / "packages" / "parcel-shell" / "tests"
if str(_SHELL_TESTS) not in sys.path:
    sys.path.insert(0, str(_SHELL_TESTS))

pytest_plugins = ["_shell_fixtures"]
