# parcel-sdk

The stable Python API surface that every Parcel module imports. Versioned independently from the shell so modules can rely on a pinned contract.

**Status:** Phase 0 skeleton. Public API is defined in Phase 6.

Planned surface:

- `Module` — declare a module (name, version, permissions, capabilities, hooks)
- `Permission` — declare a permission string + human-readable description
- `Model` / declarative base scoped to the module's schema
- `View` / `route` decorators — register HTTP routes
- `require_permission` — auth guard for routes
- Jinja + HTMX helpers
