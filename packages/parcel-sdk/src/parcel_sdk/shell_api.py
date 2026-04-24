"""Stable shell-facing surface for Parcel modules.

Modules import this facade instead of reaching into ``parcel_shell.*``.
The shell calls :func:`bind` at startup to install the real implementation;
until then every accessor raises ``RuntimeError``.

Why the registry pattern: ``parcel-sdk`` must not import ``parcel_shell`` (that
would invert the dep direction and prevent standalone install). Modules get a
typed surface; the shell stays the single provider.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from parcel_sdk.sidebar import SidebarItem

__all__ = [
    "Flash",
    "FlashKind",
    "ShellBinding",
    "SidebarItem",
    "SidebarSection",
    "bind",
    "effective_permissions",
    "get_session",
    "get_templates",
    "require_permission",
    "set_flash",
    "sidebar_for",
]

FlashKind = Literal["success", "error", "info"]


@dataclass(frozen=True)
class Flash:
    kind: FlashKind
    msg: str


@dataclass(frozen=True)
class SidebarSection:
    label: str
    items: tuple[SidebarItem, ...]


class ShellBinding(Protocol):
    def get_session(self) -> Callable[..., AsyncIterator[Any]]: ...
    def require_permission(self, name: str) -> Callable[..., Awaitable[Any]]: ...
    def set_flash(self, response: Any, flash: Flash) -> None: ...
    def get_templates(self) -> Any: ...
    def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]: ...
    async def effective_permissions(self, request: Any, user: Any) -> set[str]: ...


_impl: ShellBinding | None = None


def bind(impl: ShellBinding, *, force: bool = False) -> None:
    """Install the shell implementation. Called once at shell startup.

    Pass ``force=True`` to rebind (used by tests that rebuild the app).
    """
    global _impl
    if _impl is not None and not force:
        raise RuntimeError(
            "parcel_sdk.shell_api is already bound; pass force=True to rebind"
        )
    _impl = impl


def _need() -> ShellBinding:
    if _impl is None:
        raise RuntimeError(
            "parcel_sdk.shell_api used before shell_api.bind(); "
            "this usually means a module was imported without a shell running"
        )
    return _impl


def get_session() -> Callable[..., AsyncIterator[Any]]:
    return _need().get_session()


def require_permission(name: str) -> Callable[..., Awaitable[Any]]:
    return _need().require_permission(name)


def set_flash(response: Any, flash: Flash) -> None:
    _need().set_flash(response, flash)


def get_templates() -> Any:
    return _need().get_templates()


def sidebar_for(request: Any, perms: set[str]) -> list[SidebarSection]:
    return _need().sidebar_for(request, perms)


async def effective_permissions(request: Any, user: Any) -> set[str]:
    return await _need().effective_permissions(request, user)
