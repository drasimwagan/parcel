from __future__ import annotations

from httpx import AsyncClient


async def test_list_users_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/admin/users")
    assert r.status_code == 401


async def test_list_users_forbidden_without_permission(client: AsyncClient, user_factory) -> None:
    await user_factory(email="peon@x.com", password="password-1234")
    await client.post("/auth/login", json={"email": "peon@x.com", "password": "password-1234"})
    r = await client.get("/admin/users")
    assert r.status_code == 403


async def test_list_users_as_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(u["email"] == "admin@test.example.com" for u in body["items"])


async def test_create_user_as_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "new@x.com", "password": "password-1234", "role_ids": []},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new@x.com"
    assert body["is_active"] is True


async def test_get_user_detail(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "det@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.get(f"/admin/users/{uid}")
    assert r2.status_code == 200
    assert r2.json()["email"] == "det@x.com"


async def test_patch_user(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "patch@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.patch(
        f"/admin/users/{uid}", json={"email": "patched@x.com", "is_active": False}
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["email"] == "patched@x.com"
    assert body["is_active"] is False


async def test_delete_user_deactivates(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/users",
        json={"email": "vic@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.delete(f"/admin/users/{uid}")
    assert r2.status_code == 204
    detail = await authed_client.get(f"/admin/users/{uid}")
    assert detail.json()["is_active"] is False


async def test_assign_and_unassign_role(authed_client: AsyncClient, role_factory) -> None:
    role = await role_factory(name="editor")
    r = await authed_client.post(
        "/admin/users",
        json={"email": "rr@x.com", "password": "password-1234", "role_ids": []},
    )
    uid = r.json()["id"]
    r2 = await authed_client.post(f"/admin/users/{uid}/roles", json={"role_id": str(role.id)})
    assert r2.status_code == 204

    detail = await authed_client.get(f"/admin/users/{uid}")
    assert any(rr["name"] == "editor" for rr in detail.json()["roles"])

    r3 = await authed_client.delete(f"/admin/users/{uid}/roles/{role.id}")
    assert r3.status_code == 204
    detail2 = await authed_client.get(f"/admin/users/{uid}")
    assert all(rr["name"] != "editor" for rr in detail2.json()["roles"])
