from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import MetaData

from parcel_sdk import Module, Permission


def test_permission_is_frozen_dataclass() -> None:
    p = Permission("foo.read", "Read foo")
    assert p.name == "foo.read"
    assert p.description == "Read foo"
    with pytest.raises(Exception):
        p.name = "bar.read"  # type: ignore[misc]


def test_module_defaults() -> None:
    m = Module(name="foo", version="0.1.0")
    assert m.permissions == ()
    assert m.capabilities == ()
    assert m.alembic_ini is None
    assert m.metadata is None


def test_module_full() -> None:
    md = MetaData(schema="mod_foo")
    m = Module(
        name="foo",
        version="1.2.3",
        permissions=(Permission("foo.read", "Read"),),
        capabilities=("http_egress",),
        alembic_ini=Path("/tmp/foo/alembic.ini"),
        metadata=md,
    )
    assert m.permissions[0].name == "foo.read"
    assert m.capabilities == ("http_egress",)
    assert m.metadata is md


def test_module_is_frozen() -> None:
    m = Module(name="foo", version="0.1.0")
    with pytest.raises(Exception):
        m.version = "0.2.0"  # type: ignore[misc]


def test_module_equality_by_value() -> None:
    a = Module(name="foo", version="0.1.0", capabilities=("x",))
    b = Module(name="foo", version="0.1.0", capabilities=("x",))
    assert a == b
