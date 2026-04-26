"""Locate and run a sandbox module's optional `seed.py`.

Discovery is by file presence — `<module_root>/src/parcel_mod_<name>/seed.py`.
The sandbox loader has already imported the module; we look up the `seed`
attribute on the loaded module (which is itself a module object whose
`seed` attribute is the loaded `seed.py` submodule), then call its
`seed(session)` function.

The session passed in writes to the sandbox schema because the module's
`metadata.schema` was patched to `mod_sandbox_<uuid>` before this runs.
"""

from __future__ import annotations

import types

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

_log = structlog.get_logger("parcel_shell.sandbox.previews.seed_runner")


def has_seed(loaded_module: types.ModuleType) -> bool:
    """True iff the loaded sandbox package exposes a callable `seed.seed`."""
    seed_submodule = getattr(loaded_module, "seed", None)
    if not isinstance(seed_submodule, types.ModuleType):
        return False
    return callable(getattr(seed_submodule, "seed", None))


async def run(
    loaded_module: types.ModuleType, sessionmaker: async_sessionmaker
) -> None:
    """Open a session and await `seed(session)`. Commits via session.begin()."""
    seed_fn = loaded_module.seed.seed  # type: ignore[attr-defined]
    async with sessionmaker() as session, session.begin():
        await seed_fn(session)
    _log.info("sandbox.preview.seed_completed")
