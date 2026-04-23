"""Shell-test conftest.

Fixtures are loaded via the workspace-root conftest.py as a pytest plugin
(``_shell_fixtures``). Keeping this file empty avoids double-registering the
plugin when pytest's collection walks include this directory.
"""
