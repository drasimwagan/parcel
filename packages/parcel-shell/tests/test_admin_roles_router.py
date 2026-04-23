from __future__ import annotations

from httpx import AsyncClient


async def test_list_roles_includes_admin(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/roles")
    assert r.status_code == 200
    names = {rr["name"] for rr in r.json()}
    assert "admin" in names


async def test_create_role(authed_client: AsyncClient) -> None:
    r = await authed_client.post(
        "/admin/roles", json={"name": "editor", "description": "Edits stuff"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "editor"
    assert body["is_builtin"] is False


async def test_patch_builtin_role_is_403(authed_client: AsyncClient) -> None:
    roles = (await authed_client.get("/admin/roles")).json()
    admin = next(r for r in roles if r["name"] == "admin")
    r = await authed_client.patch(f"/admin/roles/{admin['id']}", json={"name": "renamed"})
    assert r.status_code == 403


async def test_delete_builtin_role_is_403(authed_client: AsyncClient) -> None:
    roles = (await authed_client.get("/admin/roles")).json()
    admin = next(r for r in roles if r["name"] == "admin")
    r = await authed_client.delete(f"/admin/roles/{admin['id']}")
    assert r.status_code == 403


async def test_assign_permission_to_role(authed_client: AsyncClient) -> None:
    r = await authed_client.post("/admin/roles", json={"name": "viewer", "description": None})
    rid = r.json()["id"]
    r2 = await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "users.read"}
    )
    assert r2.status_code == 204
    detail = await authed_client.get(f"/admin/roles/{rid}")
    assert "users.read" in detail.json()["permissions"]


async def test_assign_unregistered_permission_is_404(authed_client: AsyncClient) -> None:
    r = await authed_client.post("/admin/roles", json={"name": "mis", "description": None})
    rid = r.json()["id"]
    r2 = await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "bogus.perm"}
    )
    assert r2.status_code == 404


async def test_unassign_permission(authed_client: AsyncClient) -> None:
    r = await authed_client.post("/admin/roles", json={"name": "cleaner", "description": None})
    rid = r.json()["id"]
    await authed_client.post(
        f"/admin/roles/{rid}/permissions", json={"permission_name": "users.read"}
    )
    r2 = await authed_client.delete(f"/admin/roles/{rid}/permissions/users.read")
    assert r2.status_code == 204
    detail = await authed_client.get(f"/admin/roles/{rid}")
    assert "users.read" not in detail.json()["permissions"]


async def test_list_permissions(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/admin/permissions")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()}
    assert "users.read" in names and "permissions.read" in names
