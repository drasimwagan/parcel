from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.models import Company, Contact


# ── Contacts ────────────────────────────────────────────────────────────


async def list_contacts(
    db: AsyncSession, *, q: str | None = None, offset: int = 0, limit: int = 50
) -> tuple[list[Contact], int]:
    stmt = select(Contact)
    if q:
        pat = f"%{q}%"
        stmt = stmt.where(
            or_(
                Contact.email.ilike(pat),
                Contact.first_name.ilike(pat),
                Contact.last_name.ilike(pat),
            )
        )
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            stmt.order_by(Contact.created_at.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    return list(rows), int(total)


async def get_contact(db: AsyncSession, contact_id: uuid.UUID) -> Contact | None:
    return await db.get(Contact, contact_id)


async def create_contact(
    db: AsyncSession,
    *,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_id: uuid.UUID | None = None,
) -> Contact:
    c = Contact(
        email=email.lower().strip(),
        first_name=first_name or None,
        last_name=last_name or None,
        phone=phone or None,
        company_id=company_id,
    )
    db.add(c)
    await db.flush()
    return c


async def update_contact(
    db: AsyncSession,
    *,
    contact: Contact,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_id: uuid.UUID | None = None,
    clear_company: bool = False,
) -> Contact:
    if email is not None:
        contact.email = email.lower().strip()
    if first_name is not None:
        contact.first_name = first_name or None
    if last_name is not None:
        contact.last_name = last_name or None
    if phone is not None:
        contact.phone = phone or None
    if clear_company:
        contact.company_id = None
    elif company_id is not None:
        contact.company_id = company_id
    contact.updated_at = datetime.now(UTC)
    await db.flush()
    return contact


async def delete_contact(db: AsyncSession, *, contact: Contact) -> None:
    await db.delete(contact)
    await db.flush()


# ── Companies ──────────────────────────────────────────────────────────


async def list_companies(
    db: AsyncSession, *, q: str | None = None, offset: int = 0, limit: int = 50
) -> tuple[list[Company], int]:
    stmt = select(Company)
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(stmt.order_by(Company.name).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def get_company(db: AsyncSession, company_id: uuid.UUID) -> Company | None:
    return await db.get(Company, company_id)


async def create_company(
    db: AsyncSession, *, name: str, website: str | None = None
) -> Company:
    c = Company(name=name.strip(), website=(website or None))
    db.add(c)
    await db.flush()
    return c


async def update_company(
    db: AsyncSession,
    *,
    company: Company,
    name: str | None = None,
    website: str | None = None,
) -> Company:
    if name is not None:
        company.name = name.strip()
    if website is not None:
        company.website = website or None
    company.updated_at = datetime.now(UTC)
    await db.flush()
    return company


async def delete_company(db: AsyncSession, *, company: Company) -> None:
    await db.delete(company)
    await db.flush()
