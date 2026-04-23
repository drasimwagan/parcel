# Architecture

**Status:** Draft stub. Fleshed out as each phase lands.

## Layers

```
┌────────────────────────────────────────────────────────────┐
│  Admin UI (HTMX + Jinja2 + Tailwind, server-rendered)      │
├────────────────────────────────────────────────────────────┤
│  parcel-shell (FastAPI)                                     │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐  │
│  │ auth     │ │ RBAC     │ │ modules   │ │ AI authoring │  │
│  │ sessions │ │ registry │ │ loader    │ │ (Phase 7)    │  │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────┘  │
├────────────────────────────────────────────────────────────┤
│  parcel-sdk  (stable API surface for modules)               │
├────────────────────────────────────────────────────────────┤
│  Modules (pip packages, entry-point discovered)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ contacts │ │   ...    │ │   ...    │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
├────────────────────────────────────────────────────────────┤
│  Postgres (shell schema + mod_<name> per module) · Redis    │
└────────────────────────────────────────────────────────────┘
```

## Key invariants

1. The shell never imports a module by name. Discovery is via entry points only.
2. Modules never import the shell. They import `parcel-sdk` only.
3. Each module owns its Postgres schema. Cross-module data access goes through the SDK's service layer, never raw SQL or direct ORM references.
4. All state-changing code paths go through a permission check registered by a module's manifest.

TBD: details will be filled in as Phase 1–7 land.
