from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy import MetaData


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
    metadata: MetaData | None = None
