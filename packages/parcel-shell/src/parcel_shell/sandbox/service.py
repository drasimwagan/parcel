"""Sandbox pipeline — extract, gate, install, mount, promote, dismiss, prune."""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_gate import GateReport, run_gate
from parcel_shell.config import Settings
from parcel_shell.sandbox.loader import load_sandbox_module, sandbox_import_name
from parcel_shell.sandbox.models import SandboxInstall

if TYPE_CHECKING:
    from fastapi import FastAPI

    from parcel_shell.modules.models import InstalledModule

_log = structlog.get_logger("parcel_shell.sandbox.service")

SANDBOX_TTL = timedelta(days=7)
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_RATIO = 100


class GateRejected(Exception):
    """Raised when the candidate fails the gate. Holds the full report."""

    def __init__(self, report: GateReport) -> None:
        self.report = report
        super().__init__("gate rejected candidate")


class SandboxNotFound(Exception):
    pass


class TargetNameTaken(Exception):
    pass


def var_dir() -> Path:
    """Workspace runtime directory: ``<repo>/var/sandbox/``."""
    # packages/parcel-shell/src/parcel_shell/sandbox/service.py → parents[4] = repo
    return Path(__file__).resolve().parents[4] / "var" / "sandbox"


def _extract_zip(blob: bytes, dst: Path) -> None:
    if len(blob) > MAX_ZIP_BYTES:
        raise ValueError(f"zip too large: {len(blob)} bytes")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        total = sum(zi.file_size for zi in zf.infolist())
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ValueError(f"zip uncompressed too large: {total} bytes")
        if len(blob) > 0 and total / max(len(blob), 1) > MAX_RATIO:
            raise ValueError("zip compression ratio too high (bomb guard)")
        dst_resolved = dst.resolve()
        for zi in zf.infolist():
            target = (dst / zi.filename).resolve()
            if not str(target).startswith(str(dst_resolved)):
                raise ValueError(f"path traversal: {zi.filename}")
        zf.extractall(dst)


def _collapse_single_top(dst: Path) -> None:
    entries = [p for p in dst.iterdir() if p.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for p in list(inner.iterdir()):
            shutil.move(str(p), str(dst / p.name))
        inner.rmdir()


def _copy_tree(src: Path, dst: Path) -> None:
    for p in src.iterdir():
        if p.name in {"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"}:
            continue
        if p.is_dir():
            shutil.copytree(p, dst / p.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(p, dst / p.name)


def _read_manifest(root: Path) -> tuple[str, str, list[str], str]:
    """Return ``(name, version, capabilities, package_name)`` for the candidate.

    Parses ``pyproject.toml`` (authoritative for name/version) and then greps
    ``src/<pkg>/__init__.py`` or ``module.py`` with a regex for the
    ``capabilities=(...)`` literal — we must not import the candidate module
    before the gate has cleared it.
    """
    import re
    import tomllib

    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        raise ValueError("candidate has no pyproject.toml at the module root")
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    name_raw = project.get("name", "")
    if not name_raw.startswith("parcel-mod-"):
        raise ValueError(f"manifest name must start with 'parcel-mod-' (got {name_raw!r})")
    name = name_raw.removeprefix("parcel-mod-")
    version = project.get("version", "0.1.0")
    package_name = f"parcel_mod_{name}"

    search_files = [
        root / "src" / package_name / "__init__.py",
        root / "src" / package_name / "module.py",
    ]
    caps: list[str] = []
    for sf in search_files:
        if not sf.exists():
            continue
        source = sf.read_text(encoding="utf-8")
        m = re.search(r"capabilities\s*=\s*\(([^)]*)\)", source) or re.search(
            r"capabilities\s*=\s*\[([^\]]*)\]", source
        )
        if m is not None:
            caps = re.findall(r"['\"]([a-z_]+)['\"]", m.group(1))
            break
    return name, version, caps, package_name


def _mount_sandbox(app: FastAPI, module_obj, url_prefix: str) -> None:
    from parcel_shell.ui.templates import add_template_dir

    if module_obj.router is not None:
        app.include_router(module_obj.router, prefix=url_prefix)
    if module_obj.templates_dir is not None:
        add_template_dir(module_obj.templates_dir)


async def _run_sandbox_alembic(
    sandbox_root: Path,
    package_name: str,
    schema_name: str,
    settings: Settings,
    sandbox_id: uuid.UUID,
) -> None:
    """Pre-load the module with the metadata schema patched to the sandbox
    schema, alias it under the canonical name so the module's env.py resolves,
    then run ``alembic upgrade head``.
    """
    from alembic import command
    from alembic.config import Config

    short = sandbox_id.hex[:8]
    loaded = load_sandbox_module(sandbox_root, package_name, sandbox_id=short)
    if hasattr(loaded, "module") and loaded.module.metadata is not None:
        loaded.module.metadata.schema = schema_name

    # Temporarily alias the sandbox copy under the canonical import name so
    # the module's env.py (which does ``from parcel_mod_X import module``)
    # picks up the schema-patched metadata. Restore afterwards so the
    # installed copy of the module (if any) isn't shadowed.
    previous = sys.modules.get(package_name)
    sys.modules[package_name] = loaded
    try:
        ini = sandbox_root / "src" / package_name / "alembic.ini"
        cfg = Config(str(ini))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        cfg.set_main_option("script_location", str(ini.parent / "alembic"))
        await asyncio.to_thread(command.upgrade, cfg, "head")
    finally:
        if previous is not None:
            sys.modules[package_name] = previous
        else:
            sys.modules.pop(package_name, None)


async def create_sandbox(
    db: AsyncSession,
    *,
    source_zip_bytes: bytes | None = None,
    source_dir: Path | None = None,
    app: FastAPI,
    settings: Settings,
) -> SandboxInstall:
    if source_zip_bytes is None and source_dir is None:
        raise ValueError("must provide source_zip_bytes or source_dir")

    sandbox_id = uuid.uuid4()
    short_id = sandbox_id.hex[:8]
    sandbox_root = var_dir() / str(sandbox_id)
    sandbox_root.mkdir(parents=True, exist_ok=False)

    try:
        if source_zip_bytes is not None:
            _extract_zip(source_zip_bytes, sandbox_root)
            _collapse_single_top(sandbox_root)
        else:
            assert source_dir is not None
            _copy_tree(source_dir, sandbox_root)

        name, version, declared_caps, package_name = _read_manifest(sandbox_root)
        report = run_gate(sandbox_root, declared_capabilities=frozenset(declared_caps))
        if not report.passed:
            raise GateRejected(report)

        schema_name = f"mod_sandbox_{short_id}"
        url_prefix = f"/mod-sandbox/{short_id}"

        await db.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await db.flush()
        await db.commit()

        await _run_sandbox_alembic(sandbox_root, package_name, schema_name, settings, sandbox_id)

        loaded = load_sandbox_module(sandbox_root, package_name, sandbox_id=short_id)
        if hasattr(loaded, "module") and loaded.module.metadata is not None:
            loaded.module.metadata.schema = schema_name
        _mount_sandbox(app, loaded.module, url_prefix)

        now = datetime.now(UTC)
        row = SandboxInstall(
            id=sandbox_id,
            name=name,
            version=version,
            declared_capabilities=list(declared_caps),
            schema_name=schema_name,
            module_root=str(sandbox_root),
            url_prefix=url_prefix,
            gate_report=report.to_dict(),
            created_at=now,
            expires_at=now + SANDBOX_TTL,
            status="active",
        )
        db.add(row)
        await db.flush()
        _log.info("sandbox.created", id=str(sandbox_id), name=name)

        # Phase 11 — kick off preview rendering. Inline-mode short-circuits to
        # a local task; queued mode pushes onto ARQ.
        from parcel_shell.sandbox.previews.queue import enqueue as enqueue_preview

        try:
            await enqueue_preview(sandbox_id, app, settings)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "sandbox.preview.enqueue_failed",
                id=str(sandbox_id),
                error=str(exc),
            )
        return row
    except Exception:
        shutil.rmtree(sandbox_root, ignore_errors=True)
        raise


async def dismiss_sandbox(db: AsyncSession, sandbox_id: uuid.UUID, app: FastAPI) -> None:
    """Drop the sandbox schema, remove files, mark the row dismissed.

    Note: the FastAPI router stays mounted — unmounting at runtime is not
    supported. A live request to the dismissed URL will 500 when it tries to
    open a session against the dropped schema. Acceptable for Phase 7a.
    """
    row = await db.get(SandboxInstall, sandbox_id)
    if row is None:
        raise SandboxNotFound(str(sandbox_id))
    if row.status != "active":
        return  # idempotent
    await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
    shutil.rmtree(row.module_root, ignore_errors=True)
    row.status = "dismissed"
    await db.flush()
    _log.info("sandbox.dismissed", id=str(sandbox_id))


def _rewrite_package_name(
    module_dir: Path,
    orig_pkg: str,
    new_pkg: str,
    orig_name: str,
    new_name: str,
) -> None:
    """Rewrite package-name references when promoting under a different name."""
    import re

    (module_dir / "src" / orig_pkg).rename(module_dir / "src" / new_pkg)
    for ext in (".py", ".toml", ".ini", ".mako"):
        for f in module_dir.rglob(f"*{ext}"):
            source = f.read_text(encoding="utf-8")
            source = source.replace(orig_pkg, new_pkg)
            source = re.sub(
                rf'name\s*=\s*"parcel-mod-{orig_name}"',
                f'name = "parcel-mod-{new_name}"',
                source,
            )
            source = re.sub(
                rf'name\s*=\s*"{orig_name}"',
                f'name = "{new_name}"',
                source,
            )
            source = source.replace(f"mod_{orig_name}", f"mod_{new_name}")
            f.write_text(source, encoding="utf-8")


async def promote_sandbox(
    db: AsyncSession,
    sandbox_id: uuid.UUID,
    *,
    target_name: str,
    approve_capabilities: list[str],
    app: FastAPI,
    settings: Settings,
) -> InstalledModule:
    from parcel_shell.modules import service as module_service
    from parcel_shell.modules.discovery import discover_modules
    from parcel_shell.modules.models import InstalledModule

    row = await db.get(SandboxInstall, sandbox_id)
    if row is None:
        raise SandboxNotFound(str(sandbox_id))
    if row.status != "active":
        raise ValueError(f"sandbox {sandbox_id} is {row.status}, cannot promote")

    existing = await db.get(InstalledModule, target_name)
    if existing is not None:
        raise TargetNameTaken(target_name)

    repo_root = Path(__file__).resolve().parents[4]
    dst = repo_root / "modules" / target_name
    if dst.exists():
        raise TargetNameTaken(target_name)
    shutil.copytree(row.module_root, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    orig_pkg = f"parcel_mod_{row.name}"
    new_pkg = f"parcel_mod_{target_name}"
    if row.name != target_name:
        _rewrite_package_name(dst, orig_pkg, new_pkg, row.name, target_name)

    await asyncio.to_thread(
        subprocess.run,  # noqa: S603, S607
        ["uv", "pip", "install", "-e", str(dst)],
        check=True,
        capture_output=True,
        text=True,
    )

    discovered = {d.module.name: d for d in discover_modules()}
    installed = await module_service.install_module(
        db,
        name=target_name,
        approve_capabilities=approve_capabilities,
        discovered=discovered,
        database_url=settings.database_url,
        app=app,
    )

    row.status = "promoted"
    row.promoted_at = datetime.now(UTC)
    row.promoted_to_name = target_name
    await db.flush()

    await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "{row.schema_name}" CASCADE'))
    shutil.rmtree(row.module_root, ignore_errors=True)
    _log.info("sandbox.promoted", id=str(sandbox_id), target=target_name)
    return installed


async def prune_expired(db: AsyncSession, app: FastAPI, *, now: datetime) -> int:
    rows = (
        (
            await db.execute(
                select(SandboxInstall).where(
                    SandboxInstall.status == "active",
                    SandboxInstall.expires_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await dismiss_sandbox(db, row.id, app)
    return len(rows)


async def mount_sandbox_on_boot(db: AsyncSession, app: FastAPI) -> None:
    """Lifespan hook — re-mount every active sandbox."""
    rows = (
        (await db.execute(select(SandboxInstall).where(SandboxInstall.status == "active")))
        .scalars()
        .all()
    )
    for row in rows:
        sandbox_root = Path(row.module_root)
        if not sandbox_root.exists():
            _log.warning("sandbox.missing_files_at_boot", id=str(row.id))
            continue
        package_name = f"parcel_mod_{row.name}"
        short = row.id.hex[:8]
        try:
            loaded = load_sandbox_module(sandbox_root, package_name, sandbox_id=short)
            if hasattr(loaded, "module") and loaded.module.metadata is not None:
                loaded.module.metadata.schema = row.schema_name
            _mount_sandbox(app, loaded.module, row.url_prefix)
        except Exception as exc:  # noqa: BLE001
            _log.warning("sandbox.remount_failed", id=str(row.id), error=str(exc))


def _ref_sandbox_import_name() -> str:
    """Reference retained so the loader helper is importable via this module."""
    return sandbox_import_name("_", "_")
