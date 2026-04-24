"""Dynamic module loader for sandboxes.

We use :mod:`importlib.util` to load a candidate module without ``pip install
-e``, so the on-disk sandbox directory is truly throwaway. Each sandbox gets a
unique ``sys.modules`` entry (``parcel_mod_<name>__sandbox_<id>``) so two
sandboxes of the same base module can coexist.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def sandbox_import_name(package_name: str, sandbox_id: str) -> str:
    return f"{package_name}__sandbox_{sandbox_id}"


def load_sandbox_module(
    module_root: Path, package_name: str, *, sandbox_id: str
) -> types.ModuleType:
    """Load ``module_root/src/<package_name>/__init__.py`` under a per-sandbox
    import name. The base package name is aliased after loading so the module's
    own ``from parcel_mod_<name> import ...`` lines resolve correctly.
    """
    pkg_dir = module_root / "src" / package_name
    init_file = pkg_dir / "__init__.py"
    if not init_file.exists():
        raise FileNotFoundError(init_file)
    import_name = sandbox_import_name(package_name, sandbox_id)
    spec = importlib.util.spec_from_file_location(
        import_name,
        init_file,
        submodule_search_locations=[str(pkg_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"no loader for {init_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = module
    spec.loader.exec_module(module)  # importlib API — not the blocked builtin
    return module
