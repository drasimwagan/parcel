from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _zip_of(src: Path, dst: Path) -> bytes:
    with zipfile.ZipFile(dst, "w") as zf:
        for p in src.rglob("*"):
            if "__pycache__" in p.parts or p.suffix in {".pyc"}:
                continue
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(src)))
    return dst.read_bytes()


@pytest.mark.asyncio
async def test_upload_contacts_returns_201(
    committing_admin: AsyncClient, tmp_path: Path
) -> None:
    blob = _zip_of(CONTACTS_SRC, tmp_path / "contacts.zip")
    r = await committing_admin.post(
        "/admin/sandbox",
        files={"file": ("contacts.zip", blob, "application/zip")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "contacts"
    assert body["gate_report"]["passed"] is True
    sb_id = body["id"]

    # List returns it.
    r = await committing_admin.get("/admin/sandbox")
    assert r.status_code == 200
    assert any(s["id"] == sb_id for s in r.json())

    # Detail works.
    r = await committing_admin.get(f"/admin/sandbox/{sb_id}")
    assert r.status_code == 200
    assert r.json()["id"] == sb_id

    # Dismiss cleanup.
    r = await committing_admin.delete(f"/admin/sandbox/{sb_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_upload_bad_module_returns_422_with_gate_report(
    committing_admin: AsyncClient, tmp_path: Path
) -> None:
    mod = tmp_path / "bad"
    pkg = mod / "src" / "parcel_mod_bad"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "import os\nfrom parcel_sdk import Module\n"
        "module = Module(name='bad', version='0.1.0')\n"
    )
    (mod / "pyproject.toml").write_text(
        '[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n'
    )
    blob = _zip_of(mod, tmp_path / "bad.zip")
    r = await committing_admin.post(
        "/admin/sandbox",
        files={"file": ("bad.zip", blob, "application/zip")},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["gate_report"]["passed"] is False
