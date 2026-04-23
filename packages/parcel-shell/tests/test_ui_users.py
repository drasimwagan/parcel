from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def test_users_list_shows_admin(committing_admin) -> None:
    r = await committing_admin.get("/users")
    assert r.status_code == 200
    assert "@test.example.com" in r.text


async def test_create_user_via_form_redirects_to_detail(
    committing_admin, settings
) -> None:
    email = f"new-{uuid.uuid4().hex[:8]}@test.example.com"
    try:
        r = await committing_admin.post(
            "/users",
            data={"email": email, "password": "password-1234"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/users/")
        detail = await committing_admin.get(r.headers["location"])
        assert email in detail.text
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(text("DELETE FROM shell.users WHERE email = :e"), {"e": email})
            await s.commit()
        await engine.dispose()


async def test_edit_user_htmx_returns_204(committing_admin, settings) -> None:
    email = f"ed-{uuid.uuid4().hex[:8]}@test.example.com"
    try:
        r = await committing_admin.post(
            "/users",
            data={"email": email, "password": "password-1234"},
            follow_redirects=False,
        )
        uid = r.headers["location"].rsplit("/", 1)[1]
        r2 = await committing_admin.post(
            f"/users/{uid}/edit",
            data={"email": email, "is_active": "on"},
        )
        assert r2.status_code == 204
    finally:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as s:
            await s.execute(text("DELETE FROM shell.users WHERE email = :e"), {"e": email})
            await s.commit()
        await engine.dispose()
