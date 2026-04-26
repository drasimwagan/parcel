from __future__ import annotations

import importlib
import sys
import textwrap
import types
import uuid
from pathlib import Path

import pytest

from parcel_shell.sandbox.previews import seed_runner


def _make_loaded_module_with_seed_file(
    tmp_path: Path,
    seed_source: str,
) -> types.ModuleType:
    """Build a real on-disk package with a seed.py file and load it."""
    short = uuid.uuid4().hex[:8]
    pkg_name = f"fake_pkg__{short}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "seed.py").write_text(textwrap.dedent(seed_source))
    sys.path.insert(0, str(tmp_path))
    try:
        return importlib.import_module(pkg_name)
    finally:
        # Leave on sys.path so importlib.import_module(f"{pkg_name}.seed") works
        # later when seed_runner is invoked.
        pass


def test_has_seed_true_when_seed_file_exists(tmp_path: Path) -> None:
    loaded = _make_loaded_module_with_seed_file(
        tmp_path,
        """
        async def seed(session):
            return None
        """,
    )
    assert seed_runner.has_seed(loaded) is True


def test_has_seed_false_when_no_seed_file(tmp_path: Path) -> None:
    short = uuid.uuid4().hex[:8]
    pkg_name = f"fake_pkg__{short}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    sys.path.insert(0, str(tmp_path))
    pkg = importlib.import_module(pkg_name)
    assert seed_runner.has_seed(pkg) is False


def test_has_seed_false_when_seed_file_lacks_seed_callable(tmp_path: Path) -> None:
    loaded = _make_loaded_module_with_seed_file(
        tmp_path,
        """
        # No 'seed' callable defined.
        FOO = 42
        """,
    )
    assert seed_runner.has_seed(loaded) is False


@pytest.mark.asyncio
async def test_run_invokes_seed_with_session(
    tmp_path: Path, migrations_applied: str
) -> None:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    # Use a module-level list to capture across the import boundary.
    short = uuid.uuid4().hex[:8]
    pkg_name = f"fake_pkg__{short}"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "seed.py").write_text(
        textwrap.dedent(
            """
            CAPTURED = []

            async def seed(session):
                CAPTURED.append(session)
            """
        )
    )
    sys.path.insert(0, str(tmp_path))
    loaded = importlib.import_module(pkg_name)

    engine = create_async_engine(migrations_applied, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        await seed_runner.run(loaded, factory)
    finally:
        await engine.dispose()

    seed_module = importlib.import_module(f"{pkg_name}.seed")
    assert len(seed_module.CAPTURED) == 1
