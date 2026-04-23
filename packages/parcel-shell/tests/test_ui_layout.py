from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.rbac import service
from parcel_shell.rbac.models import User


async def test_admin_sees_all_sidebar_sections(committing_admin) -> None:
    r = await committing_admin.get("/")
    assert r.status_code == 200
    assert "Overview" in r.text
    assert "Access" in r.text
    assert ">Users<" in r.text
    assert ">Roles<" in r.text
    assert "System" in r.text
    assert ">Modules<" in r.text


async def test_plain_user_sees_only_dashboard(committing_client: AsyncClient, settings) -> None:
    email = f"plain-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234"
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            await service.create_user(s, email=email, password=password)
            await s.commit()

        r = await committing_client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
        assert r.status_code == 303
        r2 = await committing_client.get("/")
        assert r2.status_code == 200
        assert "Dashboard" in r2.text
        assert ">Users<" not in r2.text
        assert ">Roles<" not in r2.text
        assert ">Modules<" not in r2.text
    finally:
        async with factory() as s:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_theme_init_script_in_head(committing_admin) -> None:
    r = await committing_admin.get("/")
    assert 'localStorage.getItem("parcel_theme")' in r.text
    assert "data-theme" in r.text


async def test_active_sidebar_highlight(committing_admin) -> None:
    r = await committing_admin.get("/users")
    assert 'class="active"' in r.text
