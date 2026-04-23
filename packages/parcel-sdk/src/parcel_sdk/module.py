from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter  # noqa: F401
    from sqlalchemy import MetaData  # noqa: F401

from parcel_sdk.sidebar import SidebarItem


@dataclass(frozen=True)
class Permission:
    name: str
    description: str


@dataclass(frozen=True)
class Module:
    name: str
    version: str
    permissions: tuple[Permission, ...] = ()
    capabilities: tuple[str, ...] = ()
    alembic_ini: Path | None = None
    metadata: "MetaData | None" = None
    # Phase 5 additions — optional UI contribution:
    router: "Any | None" = None
    templates_dir: Path | None = None
    sidebar_items: tuple[SidebarItem, ...] = ()
