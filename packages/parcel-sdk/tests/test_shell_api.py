from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from parcel_sdk import shell_api
from parcel_sdk.shell_api import Flash, SidebarSection


def _fresh() -> None:
    shell_api._impl = None  # type: ignore[attr-defined]


class FakeImpl:
    def get_session(self) -> Any:
        return "SESSION_DEP"

    def require_permission(self, name: str) -> Any:
        return ("PERM_DEP", name)

    def set_flash(self, response: Any, flash: Flash) -> None:
        response["flash"] = flash

    def get_templates(self) -> Any:
        return "TPL"

    def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]:
        return [SidebarSection(label="x", items=())]

    async def effective_permissions(self, request: Any, user: Any) -> set[str]:
        return {"a", "b"}


def test_calling_before_bind_raises() -> None:
    _fresh()
    with pytest.raises(RuntimeError, match="shell_api.bind"):
        shell_api.get_session()


def test_flash_is_frozen_dataclass() -> None:
    f = Flash(kind="success", msg="ok")
    with pytest.raises(Exception):
        f.msg = "x"  # type: ignore[misc]


def test_bind_routes_calls_to_impl() -> None:
    _fresh()
    shell_api.bind(FakeImpl())
    assert shell_api.get_session() == "SESSION_DEP"
    assert shell_api.require_permission("x") == ("PERM_DEP", "x")
    resp: dict[str, Any] = {}
    shell_api.set_flash(resp, Flash(kind="info", msg="hi"))
    assert resp["flash"].msg == "hi"
    assert shell_api.get_templates() == "TPL"
    assert [s.label for s in shell_api.sidebar_for(None, set())] == ["x"]


@pytest.mark.asyncio
async def test_effective_permissions_delegates() -> None:
    _fresh()
    shell_api.bind(FakeImpl())
    perms = await shell_api.effective_permissions(None, None)
    assert perms == {"a", "b"}


def test_bind_twice_requires_force() -> None:
    _fresh()

    class Dummy:
        def get_session(self) -> Any:
            return None

        def require_permission(self, name: str) -> Any:
            return None

        def set_flash(self, response: Any, flash: Flash) -> None:
            return None

        def get_templates(self) -> Any:
            return None

        def sidebar_for(self, request: Any, perms: set[str]) -> list[SidebarSection]:
            return []

        async def effective_permissions(self, request: Any, user: Any) -> set[str]:
            return set()

    shell_api.bind(Dummy())
    with pytest.raises(RuntimeError, match="already bound"):
        shell_api.bind(Dummy())
    shell_api.bind(Dummy(), force=True)
