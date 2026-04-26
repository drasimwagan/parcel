from __future__ import annotations

import dataclasses

import pytest

from parcel_sdk import Module, PreviewRoute


def test_preview_route_constructs_with_path_only() -> None:
    pr = PreviewRoute(path="/contacts")
    assert pr.path == "/contacts"
    assert pr.title is None
    assert pr.params is None


def test_preview_route_is_frozen() -> None:
    pr = PreviewRoute(path="/contacts")
    with pytest.raises(dataclasses.FrozenInstanceError):
        pr.path = "/x"  # type: ignore[misc]


def test_preview_route_kw_only() -> None:
    with pytest.raises(TypeError):
        PreviewRoute("/contacts")  # type: ignore[misc]


def test_module_default_preview_routes_is_empty_tuple() -> None:
    m = Module(name="x", version="0.1.0")
    assert m.preview_routes == ()


def test_module_accepts_preview_routes() -> None:
    pr = PreviewRoute(path="/x", title="X page")
    m = Module(name="x", version="0.1.0", preview_routes=(pr,))
    assert m.preview_routes == (pr,)
    assert m.preview_routes[0].title == "X page"
