from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from _fake_provider import FakeProvider
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.ai.chat import service as chat_service
from parcel_shell.ai.chat.models import AISession, AITurn
from parcel_shell.config import Settings

CONTACTS_SRC = Path(__file__).resolve().parents[3] / "modules" / "contacts"


def _contacts_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for p in CONTACTS_SRC.rglob("*"):
        if "__pycache__" in p.parts or p.suffix in {".pyc"}:
            continue
        if p.is_file():
            files[str(p.relative_to(CONTACTS_SRC)).replace("\\", "/")] = p.read_bytes()
    return files


@pytest.mark.asyncio
async def test_list_page_renders(committing_admin: AsyncClient, committing_app: FastAPI) -> None:
    r = await committing_admin.get("/ai")
    assert r.status_code == 200
    assert "AI Generator" in r.text
    assert "New session" in r.text


@pytest.mark.asyncio
async def test_create_session_and_detail(
    committing_admin: AsyncClient, committing_app: FastAPI
) -> None:
    r = await committing_admin.post("/ai/sessions", follow_redirects=False)
    assert r.status_code == 303
    location = r.headers["location"]
    r = await committing_admin.get(location)
    assert r.status_code == 200
    assert "(untitled)" in r.text


@pytest.mark.asyncio
async def test_status_fragment_returns_turn_list(
    committing_admin: AsyncClient, committing_app: FastAPI, settings: Settings
) -> None:
    # Create session, add a turn directly via service (skip the background task).
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        r = await committing_admin.post("/ai/sessions", follow_redirects=False)
        sid = uuid.UUID(r.headers["location"].rsplit("/", 1)[-1])

        async with factory() as db:
            turn = await chat_service.add_turn(db, sid, "test prompt")
            await chat_service.mark_succeeded(db, turn.id, sandbox_id=uuid.uuid4())
            await db.commit()

        r = await committing_admin.get(f"/ai/sessions/{sid}/status")
        assert r.status_code == 200
        assert "Turn 1" in r.text
        assert "test prompt" in r.text
        assert "sandbox created" in r.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_add_turn_kicks_off_background_task(
    committing_admin: AsyncClient,
    committing_app: FastAPI,
    settings: Settings,
) -> None:
    committing_app.state.ai_provider = FakeProvider(queue=[_contacts_files()])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        r = await committing_admin.post("/ai/sessions", follow_redirects=False)
        sid = uuid.UUID(r.headers["location"].rsplit("/", 1)[-1])

        r = await committing_admin.post(
            f"/ai/sessions/{sid}/turns",
            data={"prompt": "track invoices"},
            follow_redirects=False,
        )
        assert r.status_code == 303

        # Wait for the background task to complete.
        for _ in range(50):
            await asyncio.sleep(0.1)
            async with factory() as db:
                turn = (
                    await db.execute(
                        # Get the single turn on this session.
                        __import__("sqlalchemy").select(AITurn).where(AITurn.session_id == sid)
                    )
                ).scalar_one_or_none()
                if turn and turn.status != "generating":
                    break
        else:
            raise AssertionError("turn stayed in generating status")

        assert turn.status == "succeeded"
        assert turn.sandbox_id is not None

        # Clean up the sandbox.
        from parcel_shell.sandbox import service as sandbox_service

        async with factory() as db:
            await sandbox_service.dismiss_sandbox(db, turn.sandbox_id, committing_app)
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_admin_session_returns_404(
    committing_admin: AsyncClient, committing_app: FastAPI, settings: Settings
) -> None:
    # Admin creates a session.
    r = await committing_admin.post("/ai/sessions", follow_redirects=False)
    sid = uuid.UUID(r.headers["location"].rsplit("/", 1)[-1])

    # Create another user and reassign the session to them.
    from parcel_shell.auth.hashing import hash_password
    from parcel_shell.rbac.models import User

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            other = User(
                id=uuid.uuid4(),
                email=f"other-{uuid.uuid4().hex[:8]}@test.example.com",
                password_hash=hash_password("password-1234-long"),
                is_active=True,
            )
            db.add(other)
            await db.flush()
            s = await db.get(AISession, sid)
            assert s is not None
            s.owner_id = other.id
            await db.commit()

        r = await committing_admin.get(f"/ai/sessions/{sid}")
        assert r.status_code == 404
    finally:
        await engine.dispose()
