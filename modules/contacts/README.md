# contacts

Demo module for Parcel — a minimal CRM (contacts, companies, notes). Exercises every shell subsystem without introducing financial/compliance risk. Becomes the fixture the AI generator is benchmarked against in Phase 7.

**Status:** Phase 0 placeholder — this README only. Implementation lands in Phase 5.

## Planned scope

- Entities: `Contact`, `Company`, `Note`
- Permissions: `contacts.read`, `contacts.write`, `contacts.delete`
- Views: list + form per entity, filtering, search
- Exercises: SDK models, Jinja views, HTMX partial updates, Alembic migrations, permission guards
