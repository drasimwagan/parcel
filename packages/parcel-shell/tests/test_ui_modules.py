from __future__ import annotations


async def test_modules_list_empty_without_patched_entry_points(committing_admin) -> None:
    r = await committing_admin.get("/modules")
    assert r.status_code == 200
    assert "Modules" in r.text


async def test_modules_list_shows_discovered(committing_admin, patch_entry_points) -> None:
    r = await committing_admin.get("/modules")
    assert r.status_code == 200
    assert ">test<" in r.text
    assert "available" in r.text


async def test_install_without_capability_shows_error_flash(
    committing_admin, patch_entry_points
) -> None:
    r = await committing_admin.post(
        "/modules/install",
        data={"name": "test"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "parcel_flash" in r.headers.get("set-cookie", "")


async def test_install_happy_path(committing_admin, patch_entry_points) -> None:
    try:
        r = await committing_admin.post(
            "/modules/install",
            data={"name": "test", "approve_capabilities": ["http_egress"]},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/modules/test"
        detail = await committing_admin.get("/modules/test")
        assert "Installed and active" in detail.text
    finally:
        await committing_admin.post("/modules/test/uninstall?drop_data=true")


async def test_uninstall_hard_via_query_param(committing_admin, patch_entry_points) -> None:
    await committing_admin.post(
        "/modules/install",
        data={"name": "test", "approve_capabilities": ["http_egress"]},
    )
    r = await committing_admin.post(
        "/modules/test/uninstall?drop_data=true", follow_redirects=False
    )
    assert r.status_code == 303
    detail = await committing_admin.get("/modules/test")
    assert "Available" in detail.text
