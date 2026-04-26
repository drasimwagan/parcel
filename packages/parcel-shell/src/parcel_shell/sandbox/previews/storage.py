"""Filesystem layout for sandbox preview screenshots.

Files live at `<module_root>/previews/<sha1prefix>_<viewport>.png`. The
SHA1 prefix is deterministic per route path (so re-renders overwrite the
same file) and filesystem-safe (no slashes, dots, or special chars).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def filename_for(route_path: str, viewport: int) -> str:
    """Deterministic, filesystem-safe filename for a route × viewport pair."""
    digest = hashlib.sha1(route_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{digest}_{viewport}.png"


def previews_dir(module_root: str) -> Path:
    return Path(module_root) / "previews"
