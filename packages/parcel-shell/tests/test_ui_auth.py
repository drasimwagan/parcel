from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from parcel_shell.rbac import service


async def test_login_page_renders(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/login")
    assert r.status_code == 200
    assert "◼ parcel" in r.text
    assert 'name="email"' in r.text


async def test_root_unauthed_redirects_to_login(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login?next=%2F")


async def test_users_unauthed_redirects_with_next(committing_client: AsyncClient) -> None:
    r = await committing_client.get("/users", follow_redirects=False)
    assert r.status_code == 303
    assert "next=%2Fusers" in r.headers["location"]


async def test_login_bad_credentials_re_renders(committing_client: AsyncClient) -> None:
    r = await committing_client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "nope-nope-nope"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "Invalid email or password" in r.text


async def test_login_success_redirects_to_dashboard(
    committing_client: AsyncClient, settings
) -> None:
    email = f"u-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234"
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            await service.create_user(s, email=email, password=password)
            await s.commit()

        r = await committing_client.post(
            "/login",
            data={"email": email, "password": password, "next": "/"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert "parcel_session" in r.cookies

        r2 = await committing_client.get("/")
        assert r2.status_code == 200
        assert "Dashboard" in r2.text
    finally:
        from parcel_shell.rbac.models import User
        async with factory() as s:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_logout_redirects_to_login(committing_admin) -> None:
    r = await committing_admin.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


async def test_profile_renders_for_authed(committing_admin) -> None:
    r = await committing_admin.get("/profile")
    assert r.status_code == 200
    assert "Change password" in r.text
