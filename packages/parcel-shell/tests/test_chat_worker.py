from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from _fake_provider import FakeProvider
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.ai.chat import service as chat_service
from parcel_shell.ai.chat.models import AITurn
from parcel_shell.ai.chat.worker import run_turn
from parcel_shell.ai.provider import ProviderError
from parcel_shell.config import Settings

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


async def _setup_turn(settings: Settings, prompt: str) -> tuple[uuid.UUID, async_sessionmaker]:
    from parcel_shell.auth.hashing import hash_password
    from parcel_shell.rbac.models import User

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"worker-{uuid.uuid4().hex[:8]}@test.example.com",
            password_hash=hash_password("password-1234-long"),
            is_active=True,
        )
        db.add(user)
        await db.flush()
        s = await chat_service.create_session(db, owner_id=user.id)
        turn = await chat_service.add_turn(db, s.id, prompt)
        await db.commit()
        return turn.id, factory


@pytest.mark.asyncio
async def test_run_turn_success_marks_succeeded(
    committing_app: FastAPI, settings: Settings
) -> None:
    turn_id, factory = await _setup_turn(settings, "track invoices")
    provider = FakeProvider(queue=[_contacts_files()])
    try:
        await run_turn(
            turn_id=turn_id,
            prompt="track invoices",
            provider=provider,
            sessionmaker=factory,
            app=committing_app,
            settings=settings,
        )
        async with factory() as db:
            turn = await db.get(AITurn, turn_id)
            assert turn is not None
            assert turn.status == "succeeded"
            assert turn.sandbox_id is not None
            # Clean up the sandbox we created.
            from parcel_shell.sandbox import service as sandbox_service

            await sandbox_service.dismiss_sandbox(db, turn.sandbox_id, committing_app)
            await db.commit()
    finally:
        await factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_run_turn_provider_error_marks_failed(
    committing_app: FastAPI, settings: Settings
) -> None:
    turn_id, factory = await _setup_turn(settings, "bad")
    provider = FakeProvider(queue=[ProviderError("network down")])
    try:
        await run_turn(
            turn_id=turn_id,
            prompt="bad",
            provider=provider,
            sessionmaker=factory,
            app=committing_app,
            settings=settings,
        )
        async with factory() as db:
            turn = await db.get(AITurn, turn_id)
            assert turn is not None
            assert turn.status == "failed"
            assert turn.failure_kind == "provider_error"
            assert "network down" in (turn.failure_message or "")
    finally:
        await factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_run_turn_gate_rejection_marks_failed_with_report(
    committing_app: FastAPI, settings: Settings
) -> None:
    turn_id, factory = await _setup_turn(settings, "bad")
    bad = {
        "pyproject.toml": (b'[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n'),
        "src/parcel_mod_bad/__init__.py": (
            b"import os\nfrom parcel_sdk import Module\n"
            b"module = Module(name='bad', version='0.1.0')\n"
        ),
    }
    provider = FakeProvider(queue=[bad, bad])
    try:
        await run_turn(
            turn_id=turn_id,
            prompt="bad",
            provider=provider,
            sessionmaker=factory,
            app=committing_app,
            settings=settings,
        )
        async with factory() as db:
            turn = await db.get(AITurn, turn_id)
            assert turn is not None
            assert turn.status == "failed"
            assert turn.failure_kind == "exceeded_retries"
            assert turn.gate_report is not None
    finally:
        await factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_run_turn_catches_unexpected_exception(
    committing_app: FastAPI, settings: Settings
) -> None:
    turn_id, factory = await _setup_turn(settings, "boom")
    provider = FakeProvider(queue=[RuntimeError("unexpected")])
    try:
        await run_turn(
            turn_id=turn_id,
            prompt="boom",
            provider=provider,
            sessionmaker=factory,
            app=committing_app,
            settings=settings,
        )
        async with factory() as db:
            turn = await db.get(AITurn, turn_id)
            assert turn is not None
            assert turn.status == "failed"
            assert turn.failure_kind == "provider_error"
            assert "unexpected" in (turn.failure_message or "")
    finally:
        await factory.kw["bind"].dispose()
