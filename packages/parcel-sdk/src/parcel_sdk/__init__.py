"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 3 surface: Module, Permission, run_async_migrations.
"""

from __future__ import annotations

from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.module import Module, Permission

__all__ = ["Module", "Permission", "run_async_migrations", "__version__"]
__version__ = "0.1.0"
