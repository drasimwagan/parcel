from __future__ import annotations

from parcel_sdk import SidebarItem

SIDEBAR_ITEMS = (
    SidebarItem(label="Contacts", href="/mod/contacts/", permission="contacts.read"),
    SidebarItem(label="Companies", href="/mod/contacts/companies", permission="contacts.read"),
)
