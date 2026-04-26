from __future__ import annotations

import types

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.sandbox.previews import seed_runner


def _make_loaded_with_seed(seed_fn) -> types.ModuleType:
    pkg = types.ModuleType("fake_pkg__sandbox_x")
    seed_module = types.ModuleType("fake_pkg__sandbox_x.seed")
    seed_module.seed = seed_fn
    pkg.seed = seed_module  # makes attribute access work
    return pkg


def test_has_seed_true_when_seed_attr_exists() -> None:
    async def _seed(_s):
        return None
    loaded = _make_loaded_with_seed(_seed)
    assert seed_runner.has_seed(loaded) is True


def test_has_seed_false_when_no_seed_attr() -> None:
    pkg = types.ModuleType("fake_pkg")
    assert seed_runner.has_seed(pkg) is False


def test_has_seed_false_when_seed_module_lacks_seed_function() -> None:
    pkg = types.ModuleType("fake_pkg")
    pkg.seed = types.ModuleType("fake_pkg.seed")  # no `seed` callable
    assert seed_runner.has_seed(pkg) is False


@pytest.mark.asyncio
async def test_run_invokes_seed_with_session(migrations_applied: str) -> None:
    captured: list[AsyncSession] = []

    async def _seed(session) -> None:
        captured.append(session)

    loaded = _make_loaded_with_seed(_seed)

    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        await seed_runner.run(loaded, factory)
    finally:
        await engine.dispose()

    assert len(captured) == 1
