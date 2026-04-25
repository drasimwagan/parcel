"""Shell-side implementation of :class:`parcel_sdk.shell_api.ShellBinding`.

Wired into the SDK registry by :func:`parcel_shell.app.create_app`; modules
reach us exclusively through ``parcel_sdk.shell_api.*``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from parcel_sdk.shell_api import Flash, SidebarSection
from parcel_shell.config import Settings
from parcel_shell.db import get_session as _get_session
from parcel_shell.rbac import service as _rbac_service
from parcel_shell.ui.dependencies import html_require_permission
from parcel_shell.ui.dependencies import set_flash as _set_flash
from parcel_shell.ui.sidebar import sidebar_for as _sidebar_for
from parcel_shell.ui.sidebar import to_sdk as _to_sdk
from parcel_shell.ui.templates import get_templates as _get_templates


class DefaultShellBinding:
    """Routes `parcel_sdk.shell_api` calls to the live shell implementation."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get_session(self) -> Callable[..., AsyncIterator[Any]]:
        return _get_session

    def require_permission(self, name: str) -> Callable[..., Awaitable[Any]]:
        return html_require_permission(name)

    def set_flash(self, response: Any, flash: Flash) -> None:
        _set_flash(response, flash, secret=self._settings.session_secret)

    def get_templates(self) -> Any:
        return _get_templates()

    def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]:
        return [_to_sdk(s) for s in _sidebar_for(request, perms)]

    async def effective_permissions(self, request: Any, user: Any) -> set[str]:
        sessionmaker = request.app.state.sessionmaker
        async with sessionmaker() as db:
            return await _rbac_service.effective_permissions(db, user.id)

    async def emit(
        self,
        session: Any,
        event: str,
        subject: Any,
        *,
        changed: tuple[str, ...] = (),
    ) -> None:
        from parcel_shell.workflows.bus import _emit_to_session

        await _emit_to_session(session, event, subject, changed=changed)
