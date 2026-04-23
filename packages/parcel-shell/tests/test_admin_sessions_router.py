from __future__ import annotations

from httpx import AsyncClient


async def test_list_sessions(
    authed_client: AsyncClient, user_factory
) -> None:
    vic = await user_factory(email="vic@x.com", password="password-1234")

    # Have the victim log in using the same client's transport to share DB state.
    import httpx

    vic_client = httpx.AsyncClient(
        transport=authed_client._transport, base_url="http://t"
    )
    await vic_client.post(
        "/auth/login", json={"email": "vic@x.com", "password": "password-1234"}
    )

    r = await authed_client.get(f"/admin/users/{vic.id}/sessions")
    assert r.status_code == 200
    assert len(r.json()) == 1
    await vic_client.aclose()


async def test_revoke_all_sessions(
    authed_client: AsyncClient, user_factory
) -> None:
    import httpx

    vic = await user_factory(email="v2@x.com", password="password-1234")
    vic_client = httpx.AsyncClient(
        transport=authed_client._transport, base_url="http://t"
    )
    await vic_client.post(
        "/auth/login", json={"email": "v2@x.com", "password": "password-1234"}
    )
    ok = await vic_client.get("/auth/me")
    assert ok.status_code == 200

    r = await authed_client.post(f"/admin/users/{vic.id}/sessions/revoke")
    assert r.status_code == 204

    denied = await vic_client.get("/auth/me")
    assert denied.status_code == 401
    await vic_client.aclose()
