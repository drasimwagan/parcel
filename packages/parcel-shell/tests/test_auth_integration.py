from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.bootstrap import create_admin_user


async def test_admin_happy_path(client: AsyncClient, db_session: AsyncSession) -> None:
    await create_admin_user(
        db_session, email="boot@x.com", password="password-1234"
    )
    await db_session.flush()

    r = await client.post(
        "/auth/login", json={"email": "boot@x.com", "password": "password-1234"}
    )
    assert r.status_code == 200

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert "users.read" in me.json()["permissions"]

    users = await client.get("/admin/users")
    assert users.status_code == 200

    await client.post("/auth/logout")

    locked = await client.get("/admin/users")
    assert locked.status_code == 401
