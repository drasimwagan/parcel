from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SidebarItem:
    label: str
    href: str
    permission: str | None


@dataclass(frozen=True)
class SidebarSection:
    label: str
    items: tuple[SidebarItem, ...]


SIDEBAR: tuple[SidebarSection, ...] = (
    SidebarSection(
        label="Overview",
        items=(SidebarItem(label="Dashboard", href="/", permission=None),),
    ),
    SidebarSection(
        label="Access",
        items=(
            SidebarItem(label="Users", href="/users", permission="users.read"),
            SidebarItem(label="Roles", href="/roles", permission="roles.read"),
        ),
    ),
    SidebarSection(
        label="System",
        items=(
            SidebarItem(label="Modules", href="/modules", permission="modules.read"),
        ),
    ),
)


def visible_sections(perms: set[str]) -> list[SidebarSection]:
    out: list[SidebarSection] = []
    for section in SIDEBAR:
        items = tuple(
            i for i in section.items if i.permission is None or i.permission in perms
        )
        if items:
            out.append(SidebarSection(label=section.label, items=items))
    return out
