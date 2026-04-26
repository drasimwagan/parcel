"""Locate and run a sandbox module's optional `seed.py`.

Discovery is by file presence — `<module_root>/src/parcel_mod_<name>/seed.py`.
The sandbox loader already exec'd the package's `__init__.py` and set up
`submodule_search_locations` on the spec, so `importlib.import_module` can
load the `seed` submodule on demand without requiring the module author to
add an explicit `from <pkg> import seed` line in `__init__.py`.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

_log = structlog.get_logger("parcel_shell.sandbox.previews.seed_runner")


def _seed_path(loaded_module: types.ModuleType) -> Path | None:
    """Find the on-disk seed.py for a loaded sandbox package, or None."""
    pkg_file = getattr(loaded_module, "__file__", None)
    if pkg_file is None:
        return None
    pkg_dir = Path(pkg_file).parent
    candidate = pkg_dir / "seed.py"
    return candidate if candidate.is_file() else None


def has_seed(loaded_module: types.ModuleType) -> bool:
    """True iff the loaded sandbox package ships a seed.py file with a
    callable `seed` function."""
    if _seed_path(loaded_module) is None:
        return False
    pkg_name = loaded_module.__name__
    try:
        seed_submodule = importlib.import_module(f"{pkg_name}.seed")
    except Exception:  # noqa: BLE001
        return False
    return callable(getattr(seed_submodule, "seed", None))


async def run(
    loaded_module: types.ModuleType, sessionmaker: async_sessionmaker
) -> None:
    """Open a session and await `seed(session)`. Commits via session.begin()."""
    pkg_name = loaded_module.__name__
    seed_submodule = importlib.import_module(f"{pkg_name}.seed")
    seed_fn = seed_submodule.seed
    async with sessionmaker() as session, session.begin():
        await seed_fn(session)
    _log.info("sandbox.preview.seed_completed")
