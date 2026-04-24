from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

from parcel_shell.sandbox.loader import load_sandbox_module, sandbox_import_name

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def test_load_sandbox_module_returns_usable_module(tmp_path: Path) -> None:
    dst = tmp_path / str(uuid.uuid4())
    shutil.copytree(CONTACTS_SRC, dst, ignore=shutil.ignore_patterns("__pycache__"))
    sb_id = uuid.uuid4().hex[:8]
    loaded = load_sandbox_module(dst, "parcel_mod_contacts", sandbox_id=sb_id)
    assert loaded.module.name == "contacts"
    assert sandbox_import_name("parcel_mod_contacts", sb_id) in sys.modules


def test_load_sandbox_module_two_sandboxes_coexist(tmp_path: Path) -> None:
    dst_a = tmp_path / "a"
    dst_b = tmp_path / "b"
    shutil.copytree(CONTACTS_SRC, dst_a, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(CONTACTS_SRC, dst_b, ignore=shutil.ignore_patterns("__pycache__"))
    a = load_sandbox_module(dst_a, "parcel_mod_contacts", sandbox_id="aaaaaaaa")
    b = load_sandbox_module(dst_b, "parcel_mod_contacts", sandbox_id="bbbbbbbb")
    assert a is not b
    assert a.module.name == b.module.name == "contacts"
