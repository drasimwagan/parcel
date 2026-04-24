from __future__ import annotations

from pathlib import Path

import pytest
from _fake_provider import FakeProvider
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.ai.generator import GenerationFailure, generate_module
from parcel_shell.ai.provider import ProviderError
from parcel_shell.config import Settings
from parcel_shell.sandbox.models import SandboxInstall

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
async def test_generator_success_first_attempt(committing_app: FastAPI, settings: Settings) -> None:
    fake = FakeProvider(queue=[_contacts_files()])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "track invoices",
                provider=fake,
                db=db,
                app=committing_app,
                settings=settings,
            )
            assert isinstance(result, SandboxInstall)
            assert result.name == "contacts"
            # Clean up
            from parcel_shell.sandbox import service as sandbox_service

            await sandbox_service.dismiss_sandbox(db, result.id, committing_app)
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generator_gate_fail_twice_returns_exceeded_retries(
    committing_app: FastAPI, settings: Settings
) -> None:
    bad_files = {
        "pyproject.toml": b'[project]\nname = "parcel-mod-bad"\nversion = "0.1.0"\n',
        "src/parcel_mod_bad/__init__.py": (
            b"import os\nfrom parcel_sdk import Module\n"
            b"module = Module(name='bad', version='0.1.0')\n"
        ),
    }
    fake = FakeProvider(queue=[bad_files, bad_files])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "bad prompt",
                provider=fake,
                db=db,
                app=committing_app,
                settings=settings,
            )
        assert isinstance(result, GenerationFailure)
        assert result.kind == "exceeded_retries"
        assert result.gate_report is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_generator_provider_error_returns_failure(
    committing_app: FastAPI, settings: Settings
) -> None:
    fake = FakeProvider(queue=[ProviderError("network borked")])
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db:
            result = await generate_module(
                "prompt",
                provider=fake,
                db=db,
                app=committing_app,
                settings=settings,
            )
        assert isinstance(result, GenerationFailure)
        assert result.kind == "provider_error"
        assert "network borked" in result.message
    finally:
        await engine.dispose()
