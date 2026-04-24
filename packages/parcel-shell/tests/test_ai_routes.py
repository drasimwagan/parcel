from __future__ import annotations

from pathlib import Path

import pytest
from _fake_provider import FakeProvider
from fastapi import FastAPI
from httpx import AsyncClient

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _contacts_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for p in CONTACTS_SRC.rglob("*"):
        if "__pycache__" in p.parts or p.suffix in {".pyc"}:
            continue
        if p.is_file():
            rel = str(p.relative_to(CONTACTS_SRC)).replace("\\", "/")
            files[rel] = p.read_bytes()
    return files


@pytest.mark.asyncio
async def test_generate_happy_path(committing_admin: AsyncClient, committing_app: FastAPI) -> None:
    committing_app.state.ai_provider = FakeProvider(queue=[_contacts_files()])
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "track invoices"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "contacts"

    # Clean up the sandbox row we just created.
    await committing_admin.delete(f"/admin/sandbox/{body['id']}")


@pytest.mark.asyncio
async def test_generate_gate_rejected_returns_422(
    committing_admin: AsyncClient, committing_app: FastAPI
) -> None:
    bad_files = {
        "pyproject.toml": (b'[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n'),
        "src/parcel_mod_bad/__init__.py": (
            b"import os\nfrom parcel_sdk import Module\n"
            b"module = Module(name='bad', version='0.1.0')\n"
        ),
    }
    committing_app.state.ai_provider = FakeProvider(queue=[bad_files, bad_files])
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "bad"})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["kind"] == "exceeded_retries"
    assert detail["gate_report"] is not None


@pytest.mark.asyncio
async def test_generate_503_when_provider_unconfigured(
    committing_admin: AsyncClient, committing_app: FastAPI
) -> None:
    committing_app.state.ai_provider = None
    r = await committing_admin.post("/admin/ai/generate", json={"prompt": "x"})
    assert r.status_code == 503
