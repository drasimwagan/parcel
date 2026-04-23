from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import SidebarItem

__all__ = [
    "SIDEBAR",
    "SidebarItem",
    "SidebarSection",
    "composed_sections",
    "sidebar_for",
    "visible_sections",
]


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
        items=(SidebarItem(label="Modules", href="/modules", permission="modules.read"),),
    ),
)


def visible_sections(perms: set[str]) -> list[SidebarSection]:
    """Shell-only sections visible to the user."""
    out: list[SidebarSection] = []
    for section in SIDEBAR:
        items = tuple(i for i in section.items if i.permission is None or i.permission in perms)
        if items:
            out.append(SidebarSection(label=section.label, items=items))
    return out


def composed_sections(
    perms: set[str],
    module_sections: dict[str, tuple[SidebarItem, ...]] | None = None,
) -> list[SidebarSection]:
    """Shell sections followed by one section per active module with visible items."""
    out = visible_sections(perms)
    if not module_sections:
        return out
    for name, items in sorted(module_sections.items()):
        visible = tuple(i for i in items if i.permission is None or i.permission in perms)
        if visible:
            out.append(SidebarSection(label=name.capitalize(), items=visible))
    return out


def sidebar_for(request, perms: set[str]) -> list[SidebarSection]:
    """Convenience: compose the sidebar using the live app state."""
    module_sections = getattr(request.app.state, "active_modules_sidebar", None)
    return composed_sections(perms, module_sections)
