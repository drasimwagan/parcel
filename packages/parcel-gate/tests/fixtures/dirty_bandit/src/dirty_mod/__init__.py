from __future__ import annotations

# B105: hardcoded password string — the fixture deliberately triggers this rule.
PASSWORD = "hunter2"


def login() -> str:
    return PASSWORD
