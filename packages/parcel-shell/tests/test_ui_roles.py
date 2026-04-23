from __future__ import annotations

import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def test_roles_list_shows_admin_role_as_builtin(committing_admin) -> None:
    r = await committing_admin.get("/roles")
    assert r.status_code == 200
    assert "admin" in r.text
    assert "built-in" in r.text


async def test_create_role_redirects_to_detail(committing_admin, settings) -> None:
    name = f"r-{uuid.uuid4().hex[:6]}"
    try:
        r = await committing_admin.post(
            "/roles",
            data={"name": name, "description": "test role"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/roles/")
        detail = await committing_admin.get(r.headers["location"])
        assert name in detail.text
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(text("DELETE FROM shell.roles WHERE name = :n"), {"n": name})
            await s.commit()
        await engine.dispose()


async def test_delete_builtin_role_shows_error_flash(committing_admin) -> None:
    roles_page = await committing_admin.get("/roles")
    m = re.search(r'href="/roles/([0-9a-f-]+)"[^>]*>admin', roles_page.text)
    assert m is not None
    admin_id = m.group(1)
    r = await committing_admin.post(f"/roles/{admin_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert "parcel_flash" in r.headers.get("set-cookie", "")
