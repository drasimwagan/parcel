"""Resolve a sandbox module's routes for screenshot capture.

Two paths:
- `module.preview_routes` is non-empty → use those declarations directly,
  calling each entry's `params` callable to fabricate URL substitutions.
- Empty → auto-walk `module.router.routes`, filter to GET, fabricate
  path-param values from the seeded data using the module's metadata.
"""

from __future__ import annotations

import re

import structlog
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk import Module

_log = structlog.get_logger("parcel_shell.sandbox.previews.routes")
_PARAM_RE = re.compile(r"\{([^}]+)\}")


async def resolve(module: Module, session: AsyncSession, schema_name: str) -> list[str]:
    """Return the ordered list of fully-substituted route paths to capture."""
    if module.preview_routes:
        return await _resolve_explicit(module, session)
    return await _resolve_auto(module, session, schema_name)


async def _resolve_explicit(module: Module, session: AsyncSession) -> list[str]:
    out: list[str] = []
    for pr in module.preview_routes:
        if "{" not in pr.path:
            out.append(pr.path)
            continue
        if pr.params is None:
            _log.debug("sandbox.preview.route_skipped", path=pr.path, reason="no_params")
            continue
        try:
            substitutions = await pr.params(session)
        except Exception as exc:  # noqa: BLE001
            _log.debug(
                "sandbox.preview.route_skipped",
                path=pr.path,
                reason="params_raised",
                error=str(exc),
            )
            continue
        substituted = _substitute(pr.path, substitutions)
        if substituted is None:
            _log.debug("sandbox.preview.route_skipped", path=pr.path, reason="missing_param")
            continue
        out.append(substituted)
    return out


async def _resolve_auto(module: Module, session: AsyncSession, schema_name: str) -> list[str]:
    if module.router is None:
        return []
    out: list[str] = []
    for route in module.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in route.methods:
            continue
        path = route.path
        params = _PARAM_RE.findall(path)
        if not params:
            out.append(path)
            continue
        substitutions = await _fabricate_params(params, module, session, schema_name)
        if substitutions is None:
            _log.debug("sandbox.preview.route_skipped", path=path, reason="missing_param")
            continue
        substituted = _substitute(path, substitutions)
        if substituted is not None:
            out.append(substituted)
    return sorted(out)


async def _fabricate_params(
    placeholders: list[str],
    module: Module,
    session: AsyncSession,
    schema_name: str,
) -> dict[str, str] | None:
    """For each placeholder, find a table whose PK column name matches and
    pull the first row's PK from the sandbox schema. Return None if any
    placeholder can't be resolved."""
    if module.metadata is None:
        return None
    out: dict[str, str] = {}
    for name in placeholders:
        value = await _lookup_first_pk(module, session, schema_name, name)
        if value is None:
            return None
        out[name] = value
    return out


async def _lookup_first_pk(
    module: Module, session: AsyncSession, schema_name: str, pk_name: str
) -> str | None:
    if module.metadata is None:
        return None
    for table in module.metadata.tables.values():
        pk_cols = [c.name for c in table.primary_key.columns]
        if pk_name not in pk_cols:
            continue
        # Run a narrow `SELECT pk LIMIT 1` against the sandbox schema. We use
        # text() because the table's metadata schema may have been patched
        # for sandbox purposes.
        try:
            row = (
                await session.execute(
                    text(
                        f'SELECT "{pk_name}" FROM "{schema_name}"."{table.name}" LIMIT 1'  # noqa: S608
                    )
                )
            ).first()
        except Exception:  # noqa: BLE001, S112
            continue
        if row is not None and row[0] is not None:
            return str(row[0])
    return None


def _substitute(path: str, values: dict[str, str]) -> str | None:
    out = path
    for placeholder in _PARAM_RE.findall(path):
        if placeholder not in values:
            return None
        out = out.replace("{" + placeholder + "}", values[placeholder])
    return out
