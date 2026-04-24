from __future__ import annotations

import pytest

from parcel_sdk import shell_api


@pytest.mark.asyncio
async def test_create_app_binds_shell_api() -> None:
    shell_api._impl = None  # type: ignore[attr-defined]
    from parcel_shell.app import create_app

    create_app()
    dep = shell_api.get_session()
    assert callable(dep)
    perm_dep = shell_api.require_permission("users.read")
    assert callable(perm_dep)
    tpl = shell_api.get_templates()
    assert hasattr(tpl, "env")


def test_set_flash_uses_session_secret() -> None:
    shell_api._impl = None  # type: ignore[attr-defined]
    from starlette.responses import Response

    from parcel_shell.app import create_app

    create_app()
    resp = Response()
    shell_api.set_flash(resp, shell_api.Flash(kind="info", msg="hello"))
    cookies = resp.headers.get("set-cookie", "")
    assert "parcel_flash=" in cookies
