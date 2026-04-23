from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import SidebarItem

__all__ = [
    "SIDEBAR",
    "SidebarItem",
    "SidebarSection",
    "active_href",
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


def active_href(path: str, sections: list[SidebarSection]) -> str | None:
    """Pick the single sidebar item href that should be highlighted for ``path``.

    Longest-prefix wins — on ``/mod/contacts/companies`` the "Companies"
    item (``/mod/contacts/companies``) wins over "Contacts" (``/mod/contacts/``).

    Trailing slashes are normalised on both sides so ``/mod/contacts`` and
    ``/mod/contacts/`` are treated as the same location.
    """
    norm_path = path.rstrip("/") or "/"
    best: str | None = None
    best_len = -1
    for section in sections:
        for item in section.items:
            norm_href = item.href.rstrip("/") or "/"
            if norm_href == norm_path:
                return item.href
            prefix = norm_href + "/" if norm_href != "/" else "/"
            # Skip root item "/" from prefix matching so it doesn't catch everything.
            if norm_href == "/":
                continue
            if (norm_path + "/").startswith(prefix) and len(norm_href) > best_len:
                best = item.href
                best_len = len(norm_href)
    return best
