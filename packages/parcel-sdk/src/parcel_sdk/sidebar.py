from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarItem:
    label: str
    href: str
    permission: str | None = None
