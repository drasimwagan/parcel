from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points

import structlog

from parcel_sdk import Module

_log = structlog.get_logger("parcel_shell.modules.discovery")


@dataclass(frozen=True)
class DiscoveredModule:
    module: Module
    distribution_name: str
    distribution_version: str


def discover_modules() -> list[DiscoveredModule]:
    """Enumerate modules exposed via the ``parcel.modules`` entry-point group.

    Bad entry points (import errors, non-Module objects) are logged and skipped
    rather than raised — shell must not fail to boot because of a third-party
    module's problem.
    """
    out: list[DiscoveredModule] = []
    for ep in entry_points(group="parcel.modules"):
        try:
            resolved = ep.load()
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "module.discovery_failed",
                entry_point=ep.name,
                error=str(exc),
            )
            continue
        if not isinstance(resolved, Module):
            _log.warning(
                "module.discovery_bad_type",
                entry_point=ep.name,
                got=type(resolved).__name__,
            )
            continue
        dist = getattr(ep, "dist", None)
        out.append(
            DiscoveredModule(
                module=resolved,
                distribution_name=dist.name if dist else ep.name,
                distribution_version=dist.version if dist else "0.0.0",
            )
        )
    return out
