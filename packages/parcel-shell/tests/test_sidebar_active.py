from __future__ import annotations

from parcel_sdk import SidebarItem
from parcel_shell.ui.sidebar import SidebarSection, active_href


def _sections() -> list[SidebarSection]:
    return [
        SidebarSection(
            label="Overview",
            items=(SidebarItem(label="Dashboard", href="/", permission=None),),
        ),
        SidebarSection(
            label="Access",
            items=(
                SidebarItem(label="Users", href="/users", permission=None),
                SidebarItem(label="Roles", href="/roles", permission=None),
            ),
        ),
        SidebarSection(
            label="Contacts",
            items=(
                SidebarItem(label="Contacts", href="/mod/contacts/", permission=None),
                SidebarItem(label="Companies", href="/mod/contacts/companies", permission=None),
            ),
        ),
    ]


def test_exact_match_wins() -> None:
    assert active_href("/users", _sections()) == "/users"


def test_longest_prefix_wins_over_ancestor() -> None:
    """Companies should win on its own URL, not Contacts."""
    assert active_href("/mod/contacts/companies", _sections()) == "/mod/contacts/companies"


def test_contacts_list_highlights_contacts() -> None:
    """The Contacts item should win on /mod/contacts/ (and /mod/contacts)."""
    assert active_href("/mod/contacts/", _sections()) == "/mod/contacts/"
    assert active_href("/mod/contacts", _sections()) == "/mod/contacts/"


def test_contact_detail_highlights_contacts_not_companies() -> None:
    """A UUID path under /mod/contacts/ should highlight Contacts, not Companies."""
    assert active_href("/mod/contacts/abc-123", _sections()) == "/mod/contacts/"


def test_company_subpath_highlights_companies() -> None:
    assert active_href("/mod/contacts/companies/xyz", _sections()) == "/mod/contacts/companies"


def test_root_dashboard_only_matches_exact() -> None:
    """The root item should only light up when we're actually at /."""
    assert active_href("/", _sections()) == "/"
    assert active_href("/users", _sections()) == "/users"
    # Must not return "/" for /users.


def test_no_match_returns_none() -> None:
    assert active_href("/unknown", _sections()) is None
