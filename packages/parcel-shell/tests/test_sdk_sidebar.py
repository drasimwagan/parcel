from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter

from parcel_sdk import Module, Permission, SidebarItem


def test_sidebar_item_shape() -> None:
    s = SidebarItem(label="Contacts", href="/mod/contacts/", permission="contacts.read")
    assert s.label == "Contacts"
    assert s.href == "/mod/contacts/"
    assert s.permission == "contacts.read"


def test_sidebar_item_optional_permission() -> None:
    s = SidebarItem(label="Dashboard", href="/", permission=None)
    assert s.permission is None


def test_module_new_fields_default_to_none_and_empty() -> None:
    m = Module(name="foo", version="0.1.0")
    assert m.router is None
    assert m.templates_dir is None
    assert m.sidebar_items == ()


def test_module_accepts_router_templates_sidebar() -> None:
    r = APIRouter()
    m = Module(
        name="foo",
        version="0.1.0",
        permissions=(Permission("foo.read", "Read foo"),),
        router=r,
        templates_dir=Path("/tmp/foo/templates"),
        sidebar_items=(SidebarItem(label="Foo", href="/mod/foo/", permission="foo.read"),),
    )
    assert m.router is r
    assert m.templates_dir == Path("/tmp/foo/templates")
    assert m.sidebar_items[0].label == "Foo"


def test_module_is_still_frozen_after_adding_fields() -> None:
    m = Module(name="foo", version="0.1.0")
    with pytest.raises(Exception):  # noqa: B017
        m.name = "bar"  # type: ignore[misc]
