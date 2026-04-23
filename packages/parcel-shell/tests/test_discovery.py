from __future__ import annotations

from importlib.metadata import EntryPoint


def test_discover_returns_fixture_module(patch_entry_points) -> None:
    from parcel_shell.modules.discovery import discover_modules

    out = discover_modules()
    assert len(out) == 1
    d = out[0]
    assert d.module.name == "test"
    assert d.module.version == "0.1.0"
    # Synthetic entry points without a real Distribution fall back to ep.name.
    assert d.distribution_name in ("parcel-mod-test", "test")


def test_discover_returns_empty_when_no_entry_points(empty_entry_points) -> None:
    from parcel_shell.modules.discovery import discover_modules

    assert discover_modules() == []


def test_discover_skips_failing_entry_points(monkeypatch) -> None:
    from parcel_shell.modules import discovery

    bad = EntryPoint(name="bad", value="nonexistent_pkg:module", group="parcel.modules")

    def fake_entry_points(*, group: str):
        return [bad] if group == "parcel.modules" else []

    monkeypatch.setattr(discovery, "entry_points", fake_entry_points)
    assert discovery.discover_modules() == []


def test_discover_skips_entry_points_returning_non_module(monkeypatch) -> None:
    from parcel_shell.modules import discovery

    ep = EntryPoint(name="wrongtype", value="typing:Any", group="parcel.modules")

    def fake_entry_points(*, group: str):
        return [ep] if group == "parcel.modules" else []

    monkeypatch.setattr(discovery, "entry_points", fake_entry_points)
    assert discovery.discover_modules() == []
