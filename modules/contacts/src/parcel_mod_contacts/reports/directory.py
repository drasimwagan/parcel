from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from parcel_mod_contacts.models import Company, Contact
from parcel_sdk import Report, ReportContext


class ContactsDirectoryParams(BaseModel):
    company: str | None = None
    created_after: date | None = None
    created_before: date | None = None


def _to_dt(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


async def directory_data(ctx: ReportContext) -> dict[str, Any]:
    p: ContactsDirectoryParams = ctx.params  # type: ignore[assignment]
    stmt = select(Contact).order_by(Contact.created_at.desc())
    if p.company:
        stmt = stmt.join(Company, Contact.company_id == Company.id).where(
            Company.name.ilike(f"%{p.company}%")
        )
    if p.created_after:
        stmt = stmt.where(Contact.created_at >= _to_dt(p.created_after))
    if p.created_before:
        stmt = stmt.where(Contact.created_at < _to_dt(p.created_before))
    contacts = list((await ctx.session.scalars(stmt)).all())

    bits: list[str] = []
    if p.company:
        bits.append(f"company contains '{p.company}'")
    if p.created_after:
        bits.append(f"after {p.created_after.isoformat()}")
    if p.created_before:
        bits.append(f"before {p.created_before.isoformat()}")
    summary = "; ".join(bits) if bits else "all contacts"

    return {
        "contacts": contacts,
        "total": len(contacts),
        "param_summary": summary,
    }


directory_report = Report(
    slug="directory",
    title="Contacts directory",
    permission="contacts.read",
    template="reports/directory.html",
    data=directory_data,
    params=ContactsDirectoryParams,
)
