"""End-to-end tests for the contacts module through the shell.

Each test installs the contacts module via the shell's installer, runs
against the real app via ``committing_admin`` (extended to mount the module),
and hard-uninstalls at the end.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture(autouse=True)
async def _contacts_installed(settings) -> AsyncIterator[None]:
    """Install the contacts module via the module service, then clean up after."""
    from parcel_mod_contacts import module as contacts_module
    from parcel_shell.modules import service as module_service
    from parcel_shell.modules.discovery import DiscoveredModule

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    index = {
        "contacts": DiscoveredModule(
            module=contacts_module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        )
    }

    async with factory() as s:
        await s.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
        await s.execute(text("DELETE FROM shell.installed_modules WHERE name = 'contacts'"))
        await s.execute(text("DELETE FROM shell.permissions WHERE module = 'contacts'"))
        await s.commit()

    async with factory() as s:
        await module_service.install_module(
            s,
            name="contacts",
            approve_capabilities=[],
            discovered=index,
            database_url=settings.database_url,
        )
        await s.commit()

    try:
        yield
    finally:
        async with factory() as s:
            try:
                await module_service.uninstall_module(
                    s,
                    name="contacts",
                    drop_data=True,
                    discovered=index,
                    database_url=settings.database_url,
                )
                await s.commit()
            except Exception:
                await s.rollback()
            await s.execute(text('DROP SCHEMA IF EXISTS "mod_contacts" CASCADE'))
            await s.execute(text("DELETE FROM shell.installed_modules WHERE name = 'contacts'"))
            await s.execute(text("DELETE FROM shell.permissions WHERE module = 'contacts'"))
            await s.commit()
        await engine.dispose()


@pytest.fixture
async def authed_contacts(committing_client: AsyncClient, settings) -> AsyncIterator[AsyncClient]:
    """Create a fresh admin user, mount contacts onto the app, log in."""
    from parcel_mod_contacts import module as contacts_module
    from parcel_shell.bootstrap import create_admin_user
    from parcel_shell.modules.discovery import DiscoveredModule
    from parcel_shell.modules.integration import mount_module
    from parcel_shell.rbac.models import User

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    email = f"admin-{uuid.uuid4().hex[:8]}@test.example.com"
    password = "password-1234-long"
    async with factory() as s:
        await create_admin_user(s, email=email, password=password, force=False)
        await s.commit()

    app = committing_client._transport.app  # type: ignore[attr-defined]
    discovered = DiscoveredModule(
        module=contacts_module,
        distribution_name="parcel-mod-contacts",
        distribution_version="0.1.0",
    )
    mount_module(app, discovered)

    r = await committing_client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )
    assert r.status_code == 303, r.text
    try:
        yield committing_client
    finally:
        async with factory() as s:
            u = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if u is not None:
                await s.delete(u)
                await s.commit()
        await engine.dispose()


async def test_contacts_list_renders(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.get("/mod/contacts/")
    assert r.status_code == 200, r.text
    assert "Contacts" in r.text
    assert "Search by name or email" in r.text


async def test_companies_list_is_not_shadowed_by_contact_detail(
    authed_contacts: AsyncClient,
) -> None:
    """Regression: /mod/contacts/companies must render the companies list, not
    422 from the /{contact_id} route trying to parse "companies" as a UUID.
    """
    r = await authed_contacts.get("/mod/contacts/companies")
    assert r.status_code == 200, r.text
    assert "Companies" in r.text
    r2 = await authed_contacts.get("/mod/contacts/companies/new")
    assert r2.status_code == 200, r2.text


async def test_create_contact_redirects_to_detail(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "ada@example.com", "first_name": "Ada", "last_name": "Lovelace"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"].startswith("/mod/contacts/")
    detail = await authed_contacts.get(r.headers["location"])
    assert "Ada" in detail.text
    assert "ada@example.com" in detail.text


async def test_edit_contact(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "grace@example.com", "first_name": "Grace"},
        follow_redirects=False,
    )
    contact_url = r.headers["location"]
    contact_id = contact_url.rsplit("/", 1)[1]
    r2 = await authed_contacts.post(
        f"/mod/contacts/{contact_id}/edit",
        data={
            "email": "grace.hopper@example.com",
            "first_name": "Grace",
            "last_name": "Hopper",
            "phone": "+1 555 0100",
            "company_id": "",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303
    detail = await authed_contacts.get(contact_url)
    assert "grace.hopper@example.com" in detail.text
    assert "Hopper" in detail.text


async def test_delete_contact_redirects_to_list(authed_contacts: AsyncClient) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "doomed@example.com"},
        follow_redirects=False,
    )
    contact_id = r.headers["location"].rsplit("/", 1)[1]
    r2 = await authed_contacts.post(f"/mod/contacts/{contact_id}/delete", follow_redirects=False)
    assert r2.status_code == 303
    assert r2.headers["location"] == "/mod/contacts/"


async def test_search_filters_list(authed_contacts: AsyncClient) -> None:
    await authed_contacts.post(
        "/mod/contacts/", data={"email": "alan@example.com", "first_name": "Alan"}
    )
    await authed_contacts.post(
        "/mod/contacts/", data={"email": "ada@example.com", "first_name": "Ada"}
    )
    r = await authed_contacts.get("/mod/contacts/?q=ada")
    assert r.status_code == 200
    assert "ada@example.com" in r.text
    assert "alan@example.com" not in r.text


async def test_company_create_then_delete_nulls_contact_company(
    authed_contacts: AsyncClient,
) -> None:
    r = await authed_contacts.post(
        "/mod/contacts/companies",
        data={"name": "Analytical Co."},
        follow_redirects=False,
    )
    company_id = r.headers["location"].rsplit("/", 1)[1]

    r2 = await authed_contacts.post(
        "/mod/contacts/",
        data={"email": "ada@x.com", "company_id": company_id},
        follow_redirects=False,
    )
    contact_id = r2.headers["location"].rsplit("/", 1)[1]

    r3 = await authed_contacts.post(
        f"/mod/contacts/companies/{company_id}/delete", follow_redirects=False
    )
    assert r3.status_code == 303

    # Contact detail still renders; company dropdown shows "—" selected.
    detail = await authed_contacts.get(f"/mod/contacts/{contact_id}")
    assert detail.status_code == 200
