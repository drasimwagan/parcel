"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 5 surface: Module, Permission, SidebarItem, run_async_migrations.
"""

from __future__ import annotations

from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.module import Module, Permission
from parcel_sdk.sidebar import SidebarItem

__all__ = ["Module", "Permission", "SidebarItem", "run_async_migrations", "__version__"]
__version__ = "0.2.0"
