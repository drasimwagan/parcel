from __future__ import annotations

from httpx import AsyncClient


async def test_login_success_sets_cookie(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    r = await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    assert r.status_code == 200
    assert "parcel_session" in r.cookies
    body = r.json()
    assert body["user"]["email"] == "ok@x.com"
    assert body["permissions"] == []


async def test_login_bad_password_is_401(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    r = await client.post("/auth/login", json={"email": "ok@x.com", "password": "nope-nope"})
    assert r.status_code == 401


async def test_login_inactive_user_is_401(client: AsyncClient, user_factory) -> None:
    await user_factory(email="off@x.com", password="password-1234", is_active=False)
    r = await client.post("/auth/login", json={"email": "off@x.com", "password": "password-1234"})
    assert r.status_code == 401


async def test_login_unknown_email_is_401(client: AsyncClient) -> None:
    r = await client.post(
        "/auth/login", json={"email": "missing@x.com", "password": "password-1234"}
    )
    assert r.status_code == 401


async def test_me_without_cookie_is_401(client: AsyncClient) -> None:
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_with_cookie_returns_user(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "ok@x.com"


async def test_logout_clears_cookie_and_invalidates_session(
    client: AsyncClient, user_factory
) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post("/auth/logout")
    assert r.status_code == 204
    r2 = await client.get("/auth/me")
    assert r2.status_code == 401


async def test_change_password_wrong_current_is_400(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-password-1234"},
    )
    assert r.status_code == 400


async def test_change_password_success(client: AsyncClient, user_factory) -> None:
    await user_factory(email="ok@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "ok@x.com", "password": "password-1234"})
    r = await client.post(
        "/auth/change-password",
        json={"current_password": "password-1234", "new_password": "new-password-1234"},
    )
    assert r.status_code == 204
    await client.post("/auth/logout")
    r2 = await client.post(
        "/auth/login", json={"email": "ok@x.com", "password": "new-password-1234"}
    )
    assert r2.status_code == 200
