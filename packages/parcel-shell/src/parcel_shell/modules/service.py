from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.models import InstalledModule
from parcel_shell.rbac.models import Permission

_log = structlog.get_logger("parcel_shell.modules.service")


class ModuleNotDiscovered(Exception):
    pass


class ModuleAlreadyInstalled(Exception):
    pass


class CapabilityMismatch(Exception):
    pass


class ModuleMigrationFailed(Exception):
    pass


def _alembic_config(database_url: str, discovered: DiscoveredModule) -> Config:
    ini = discovered.module.alembic_ini
    if ini is None:
        raise ValueError(f"module {discovered.module.name!r} has no alembic_ini")
    cfg = Config(str(ini))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def install_module(
    db: AsyncSession,
    *,
    name: str,
    approve_capabilities: list[str],
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> InstalledModule:
    d = discovered.get(name)
    if d is None:
        raise ModuleNotDiscovered(name)
    if await db.get(InstalledModule, name) is not None:
        raise ModuleAlreadyInstalled(name)
    if set(approve_capabilities) != set(d.module.capabilities):
        raise CapabilityMismatch(
            f"declared={sorted(d.module.capabilities)!r} approved={sorted(approve_capabilities)!r}"
        )

    schema = f"mod_{name}"
    await db.execute(sa_text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    if d.module.permissions:
        stmt = pg_insert(Permission).values(
            [
                {"name": p.name, "description": p.description, "module": name}
                for p in d.module.permissions
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Permission.name],
            set_={
                "description": stmt.excluded.description,
                "module": stmt.excluded.module,
            },
        )
        await db.execute(stmt)

    # The module's migrations open their own connection; they must see the
    # CREATE SCHEMA we just issued. Flush + commit before running them.
    await db.flush()
    await db.commit()

    cfg = _alembic_config(database_url, d)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        _log.exception("module.install_migration_failed", name=name, error=str(exc))
        # Best-effort cleanup of what we committed.
        await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.execute(
            sa_text("DELETE FROM shell.permissions WHERE module = :name"),
            {"name": name},
        )
        await db.commit()
        raise ModuleMigrationFailed(str(exc)) from exc

    head = ScriptDirectory.from_config(cfg).get_current_head()
    now = datetime.now(UTC)
    row = InstalledModule(
        name=name,
        version=d.module.version,
        is_active=True,
        capabilities=sorted(set(approve_capabilities)),
        schema_name=schema,
        installed_at=now,
        updated_at=now,
        last_migrated_at=now,
        last_migrated_rev=head,
    )
    db.add(row)
    await db.flush()
    return row


async def upgrade_module(
    db: AsyncSession,
    *,
    name: str,
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> InstalledModule:
    row = await db.get(InstalledModule, name)
    if row is None:
        raise ModuleNotDiscovered(name)
    d = discovered.get(name)
    if d is None:
        raise ModuleNotDiscovered(name)

    cfg = _alembic_config(database_url, d)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        _log.exception("module.upgrade_failed", name=name, error=str(exc))
        raise ModuleMigrationFailed(str(exc)) from exc

    head = ScriptDirectory.from_config(cfg).get_current_head()
    now = datetime.now(UTC)
    row.version = d.module.version
    row.updated_at = now
    row.last_migrated_at = now
    row.last_migrated_rev = head
    await db.flush()
    return row


async def uninstall_module(
    db: AsyncSession,
    *,
    name: str,
    drop_data: bool = False,
    discovered: dict[str, DiscoveredModule],
    database_url: str,
) -> None:
    row = await db.get(InstalledModule, name)
    if row is None:
        raise ModuleNotDiscovered(name)

    now = datetime.now(UTC)

    if not drop_data:
        row.is_active = False
        row.updated_at = now
        await db.flush()
        return

    d = discovered.get(name)
    if d is not None:
        cfg = _alembic_config(database_url, d)
        try:
            await asyncio.to_thread(command.downgrade, cfg, "base")
        except Exception as exc:  # noqa: BLE001
            _log.warning("module.downgrade_skipped", name=name, error=str(exc))

    await db.execute(sa_text(f'DROP SCHEMA IF EXISTS "mod_{name}" CASCADE'))
    await db.execute(
        sa_text("DELETE FROM shell.permissions WHERE module = :name"),
        {"name": name},
    )
    await db.delete(row)
    await db.flush()


async def sync_on_boot(
    db: AsyncSession,
    *,
    discovered: dict[str, DiscoveredModule] | None = None,
) -> None:
    """Flip rows whose module is no longer entry-point-discoverable to inactive."""
    if discovered is None:
        from parcel_shell.modules.discovery import discover_modules

        discovered = {d.module.name: d for d in discover_modules()}

    rows = (
        (await db.execute(select(InstalledModule).where(InstalledModule.is_active.is_(True))))
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        if row.name not in discovered:
            _log.warning("module.missing", name=row.name)
            row.is_active = False
            row.updated_at = now
    await db.flush()
