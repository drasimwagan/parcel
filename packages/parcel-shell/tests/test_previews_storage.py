from __future__ import annotations

from pathlib import Path

from parcel_shell.sandbox.previews import storage


def test_filename_for_is_deterministic() -> None:
    a = storage.filename_for("/contacts", 375)
    b = storage.filename_for("/contacts", 375)
    assert a == b


def test_filename_for_includes_viewport() -> None:
    assert storage.filename_for("/x", 375).endswith("_375.png")
    assert storage.filename_for("/x", 768).endswith("_768.png")
    assert storage.filename_for("/x", 1280).endswith("_1280.png")


def test_filename_for_distinguishes_routes() -> None:
    assert storage.filename_for("/contacts", 375) != storage.filename_for("/contacts/new", 375)


def test_filename_for_path_safe() -> None:
    name = storage.filename_for("/contacts/{id}", 375)
    assert "/" not in name
    assert "\\" not in name
    assert ".." not in name


def test_previews_dir_under_module_root(tmp_path: Path) -> None:
    module_root = tmp_path / "sandbox-foo"
    module_root.mkdir()
    d = storage.previews_dir(str(module_root))
    assert d == module_root / "previews"
