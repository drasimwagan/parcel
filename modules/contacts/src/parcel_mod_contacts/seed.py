"""Sample data for the sandbox preview renderer.

Imported and run by ``parcel_shell.sandbox.previews.seed_runner`` after the
sandbox schema is created.  Idempotency is not required — the renderer only
seeds on first install; subsequent re-renders skip the seed call because the
runner does not re-run seed on its own.

Schema patching: by the time this function is called the runner has already
set ``module.metadata.schema = "mod_sandbox_<uuid>"``, so every INSERT goes
to the sandbox schema, never to the production ``mod_contacts`` schema.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.models import Company, Contact


async def seed(session: AsyncSession) -> None:
    """Populate sample companies and contacts for the sandbox preview."""

    # --- companies -----------------------------------------------------------
    acme = Company(name="Acme Corp", website="https://acme.example.com")
    globex = Company(name="Globex Industries", website="https://globex.example.com")
    initech = Company(name="Initech LLC", website=None)

    session.add_all([acme, globex, initech])
    await session.flush()  # assign PKs so contacts can reference them

    # --- contacts ------------------------------------------------------------
    contacts = [
        Contact(
            email="alice.walker@acme.example.com",
            first_name="Alice",
            last_name="Walker",
            phone="+1-555-0101",
            company_id=acme.id,
        ),
        Contact(
            email="bob.chen@acme.example.com",
            first_name="Bob",
            last_name="Chen",
            phone="+1-555-0102",
            company_id=acme.id,
        ),
        Contact(
            email="carol.dasilva@globex.example.com",
            first_name="Carol",
            last_name="Da Silva",
            phone="+1-555-0201",
            company_id=globex.id,
        ),
        Contact(
            email="dave.kim@initech.example.com",
            first_name="Dave",
            last_name="Kim",
            phone=None,
            company_id=initech.id,
        ),
        Contact(
            email="eve.okonkwo@initech.example.com",
            first_name="Eve",
            last_name="Okonkwo",
            phone="+1-555-0301",
            company_id=initech.id,
        ),
        Contact(
            email="frank.muller@example.com",
            first_name="Frank",
            last_name="Müller",
            phone="+49-30-555-0401",
            company_id=None,  # independent / no company
        ),
        Contact(
            email="grace.li@example.com",
            first_name="Grace",
            last_name="Li",
            phone=None,
            company_id=None,
        ),
    ]

    session.add_all(contacts)
    # Caller (seed_runner) commits the session after this function returns.
