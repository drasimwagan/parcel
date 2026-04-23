# Module Authoring Guide

**Status:** Stub. Authoring API is defined in Phase 6; this doc grows alongside the SDK.

## What a Parcel module is

A pip-installable Python package that:

1. Depends on `parcel-sdk`.
2. Exposes a `Module` object via the `parcel.modules` entry point.
3. Owns its own Postgres schema and Alembic migration directory.
4. Declares its permissions and capabilities in the manifest.

## Minimal example (preview — not yet runnable)

```python
# modules/notes/src/parcel_mod_notes/__init__.py
from parcel_sdk import Module, Permission

module = Module(
    name="notes",
    version="0.1.0",
    permissions=[
        Permission("notes.read", "View notes"),
        Permission("notes.write", "Create and edit notes"),
    ],
    capabilities=[],  # Declare e.g., ["http_egress"] if you need outbound HTTP
)
```

```toml
# modules/notes/pyproject.toml
[project]
name = "parcel-mod-notes"
version = "0.1.0"
dependencies = ["parcel-sdk"]

[project.entry-points."parcel.modules"]
notes = "parcel_mod_notes:module"
```

Full authoring API — models, views, templates, migrations, hooks — lands in Phase 6. This file will be expanded then.
