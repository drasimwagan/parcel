from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.sandbox.models import SandboxInstall


async def _seed_sandbox(
    db: AsyncSession,
    *,
    preview_status: str = "ready",
    previews: list[dict] | None = None,
    module_root: str = "/tmp/sandbox-test",
) -> uuid.UUID:
    sb_id = uuid.uuid4()
    schema_name = f"mod_sandbox_{sb_id.hex[:8]}"
    db.add(
        SandboxInstall(
            id=sb_id,
            name="t",
            version="0.1.0",
            declared_capabilities=[],
            schema_name=schema_name,
            module_root=module_root,
            url_prefix="/mod-sandbox/abc",
            gate_report={"passed": True, "findings": []},
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=7),
            status="active",
            preview_status=preview_status,
            previews=previews or [],
        )
    )
    await db.flush()
    return sb_id


@pytest.mark.asyncio
async def test_previews_fragment_polls_when_rendering(authed_client, db_session) -> None:
    sb_id = await _seed_sandbox(db_session, preview_status="rendering")
    r = await authed_client.get(f"/sandbox/{sb_id}/previews-fragment")
    assert r.status_code == 200
    body = r.text
    assert 'hx-get="/sandbox/' in body
    assert 'hx-trigger="every 2s"' in body


@pytest.mark.asyncio
async def test_previews_fragment_no_polling_when_terminal(authed_client, db_session) -> None:
    sb_id = await _seed_sandbox(db_session, preview_status="ready")
    r = await authed_client.get(f"/sandbox/{sb_id}/previews-fragment")
    assert r.status_code == 200
    assert 'hx-trigger="every 2s"' not in r.text


@pytest.mark.asyncio
async def test_render_endpoint_refuses_when_already_rendering(authed_client, db_session) -> None:
    sb_id = await _seed_sandbox(db_session, preview_status="rendering")
    r = await authed_client.post(f"/sandbox/{sb_id}/previews/render", follow_redirects=False)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_render_endpoint_clears_state_and_redirects(
    authed_client, db_session, monkeypatch
) -> None:
    from unittest.mock import AsyncMock, patch

    sb_id = await _seed_sandbox(
        db_session,
        preview_status="ready",
        previews=[{"route": "/x", "viewport": 375, "filename": "f.png", "status": "ok"}],
    )
    fake = AsyncMock()
    with patch("parcel_shell.sandbox.previews.queue.enqueue", fake):
        r = await authed_client.post(f"/sandbox/{sb_id}/previews/render", follow_redirects=False)
    assert r.status_code == 303
    fake.assert_awaited_once()


@pytest.mark.asyncio
async def test_preview_image_404_for_unknown_filename(authed_client, db_session) -> None:
    sb_id = await _seed_sandbox(db_session, preview_status="ready")
    r = await authed_client.get(f"/sandbox/{sb_id}/preview-image/unknown.png")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_image_streams_when_known(authed_client, db_session, tmp_path: Path) -> None:
    module_root = tmp_path / "sandbox-img"
    (module_root / "previews").mkdir(parents=True)
    img = module_root / "previews" / "abc123_375.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    sb_id = await _seed_sandbox(
        db_session,
        preview_status="ready",
        previews=[{"route": "/x", "viewport": 375, "filename": "abc123_375.png", "status": "ok"}],
        module_root=str(module_root),
    )
    r = await authed_client.get(f"/sandbox/{sb_id}/preview-image/abc123_375.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_preview_image_rejects_errored_entry_filename(authed_client, db_session) -> None:
    sb_id = await _seed_sandbox(
        db_session,
        preview_status="ready",
        previews=[{"route": "/x", "viewport": 375, "filename": None, "status": "error"}],
    )
    r = await authed_client.get(f"/sandbox/{sb_id}/preview-image/anything.png")
    assert r.status_code == 404
