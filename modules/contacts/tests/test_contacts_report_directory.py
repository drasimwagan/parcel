from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.models import Company, Contact
from parcel_mod_contacts.reports.directory import (
    ContactsDirectoryParams,
    directory_data,
)
from parcel_sdk import ReportContext

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession) -> dict[str, Contact]:
    """Seed two companies and three contacts spread across two days."""
    now = datetime.now(tz=UTC)
    acme = Company(id=uuid4(), name="Acme")
    globex = Company(id=uuid4(), name="Globex")
    session.add_all([acme, globex])
    await session.flush()

    alice = Contact(
        id=uuid4(),
        first_name="Alice",
        last_name="A",
        email="alice@a.com",
        company_id=acme.id,
    )
    bob = Contact(
        id=uuid4(),
        first_name="Bob",
        last_name="B",
        email="bob@a.com",
        company_id=acme.id,
    )
    carol = Contact(
        id=uuid4(),
        first_name="Carol",
        last_name="C",
        email="carol@g.com",
        company_id=globex.id,
    )
    session.add_all([alice, bob, carol])
    await session.flush()

    # Force chronological ordering: alice oldest, bob middle, carol newest.
    await session.execute(
        Contact.__table__.update()
        .where(Contact.id == alice.id)
        .values(created_at=now - timedelta(days=2))
    )
    await session.execute(
        Contact.__table__.update()
        .where(Contact.id == bob.id)
        .values(created_at=now - timedelta(days=1))
    )
    await session.execute(
        Contact.__table__.update().where(Contact.id == carol.id).values(created_at=now)
    )
    await session.commit()
    return {"alice": alice, "bob": bob, "carol": carol}


async def test_directory_no_filters_returns_all(contacts_session: AsyncSession) -> None:
    await _seed(contacts_session)
    ctx = ReportContext(session=contacts_session, user_id=uuid4(), params=ContactsDirectoryParams())
    out = await directory_data(ctx)
    assert out["total"] == 3
    names = [c.first_name for c in out["contacts"]]
    assert names == ["Carol", "Bob", "Alice"]
    assert "all contacts" in out["param_summary"]


async def test_directory_company_filter_case_insensitive(
    contacts_session: AsyncSession,
) -> None:
    await _seed(contacts_session)
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="acme"),
    )
    out = await directory_data(ctx)
    assert {c.first_name for c in out["contacts"]} == {"Alice", "Bob"}
    assert "company" in out["param_summary"]


async def test_directory_created_after_inclusive(
    contacts_session: AsyncSession,
) -> None:
    await _seed(contacts_session)
    yesterday = (datetime.now(tz=UTC) - timedelta(days=1)).date()
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(created_after=yesterday),
    )
    out = await directory_data(ctx)
    assert {c.first_name for c in out["contacts"]} == {"Bob", "Carol"}


async def test_directory_created_before_exclusive(
    contacts_session: AsyncSession,
) -> None:
    await _seed(contacts_session)
    today = datetime.now(tz=UTC).date()
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(created_before=today),
    )
    out = await directory_data(ctx)
    # Today (Carol) is excluded; yesterday + 2 days ago remain.
    assert {c.first_name for c in out["contacts"]} == {"Alice", "Bob"}


async def test_directory_combined_filters_and(
    contacts_session: AsyncSession,
) -> None:
    await _seed(contacts_session)
    yesterday = (datetime.now(tz=UTC) - timedelta(days=1)).date()
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="Acme", created_after=yesterday),
    )
    out = await directory_data(ctx)
    assert [c.first_name for c in out["contacts"]] == ["Bob"]


async def test_directory_empty_result(contacts_session: AsyncSession) -> None:
    ctx = ReportContext(
        session=contacts_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="DoesNotExist"),
    )
    out = await directory_data(ctx)
    assert out["total"] == 0
    assert out["contacts"] == []
