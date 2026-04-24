from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts import service


async def test_create_and_get_contact(contacts_session: AsyncSession) -> None:
    c = await service.create_contact(contacts_session, email="Ada@Example.com", first_name="Ada")
    await contacts_session.commit()
    assert c.email == "ada@example.com"
    got = await service.get_contact(contacts_session, c.id)
    assert got is not None and got.email == "ada@example.com"


async def test_list_contacts_search(contacts_session: AsyncSession) -> None:
    await service.create_contact(contacts_session, email="a@x.com", first_name="Ada")
    await service.create_contact(contacts_session, email="b@x.com", first_name="Bob")
    await contacts_session.commit()
    rows, total = await service.list_contacts(contacts_session, q="ada")
    assert len(rows) == 1 and rows[0].first_name == "Ada"
    assert total == 1


async def test_create_and_link_company(contacts_session: AsyncSession) -> None:
    co = await service.create_company(contacts_session, name="Analytical Co.")
    await contacts_session.commit()
    c = await service.create_contact(
        contacts_session, email="ada@x.com", first_name="Ada", company_id=co.id
    )
    await contacts_session.commit()
    got = await service.get_contact(contacts_session, c.id)
    assert got is not None and got.company_id == co.id


async def test_company_delete_sets_contact_company_null(
    contacts_session: AsyncSession,
) -> None:
    co = await service.create_company(contacts_session, name="Doomed Inc.")
    c = await service.create_contact(contacts_session, email="x@x.com", company_id=co.id)
    await contacts_session.commit()
    contact_id = c.id

    await service.delete_company(contacts_session, company=co)
    await contacts_session.commit()
    contacts_session.expire_all()

    refreshed = await service.get_contact(contacts_session, contact_id)
    assert refreshed is not None
    assert refreshed.company_id is None


async def test_update_contact_clears_company_on_request(
    contacts_session: AsyncSession,
) -> None:
    co = await service.create_company(contacts_session, name="Temporary")
    c = await service.create_contact(contacts_session, email="y@x.com", company_id=co.id)
    await contacts_session.commit()

    await service.update_contact(contacts_session, contact=c, clear_company=True)
    await contacts_session.commit()
    got = await service.get_contact(contacts_session, c.id)
    assert got is not None and got.company_id is None
