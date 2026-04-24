"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 6 surface: Module, Permission, SidebarItem, run_async_migrations, shell_api.
"""

from __future__ import annotations

from parcel_sdk import shell_api
from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.module import Module, Permission
from parcel_sdk.sidebar import SidebarItem

__all__ = [
    "Module",
    "Permission",
    "SidebarItem",
    "__version__",
    "run_async_migrations",
    "shell_api",
]
__version__ = "0.3.0"
