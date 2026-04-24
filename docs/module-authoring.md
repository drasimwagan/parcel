# Module Authoring Guide

**Status:** Current through Phase 6. The SDK surface is stable at `parcel-sdk` 0.3.x.

## What a Parcel module is

A pip-installable Python package that:

1. Depends only on `parcel-sdk` (not `parcel-shell`).
2. Exposes a `Module` object via the `parcel.modules` entry point.
3. Owns its own Postgres schema (`mod_<name>`) and Alembic migration directory.
4. Declares its permissions and capabilities in the manifest.

## Quickstart — scaffold with the CLI

```bash
uv run parcel new-module widgets
uv sync --all-packages
uv run parcel install ./modules/widgets
uv run parcel dev
# visit http://localhost:8000/mod/widgets/
```

`parcel new-module` writes:

```
modules/widgets/
  pyproject.toml                          # parcel-sdk dep, entry point to parcel_mod_widgets:module
  README.md
  src/parcel_mod_widgets/
    __init__.py                           # exports `module`
    module.py                             # Module(...) manifest
    models.py                             # DeclarativeBase bound to mod_widgets schema
    router.py                             # APIRouter; one hello-world view
    alembic.ini                           # points at ./alembic
    alembic/
      env.py                              # calls parcel_sdk.alembic_env.run_async_migrations
      script.py.mako
      versions/0001_init.py               # CREATE SCHEMA IF NOT EXISTS "mod_widgets"
    templates/widgets/index.html
  tests/test_smoke.py
```

## The `Module` manifest

```python
# modules/widgets/src/parcel_mod_widgets/__init__.py
from pathlib import Path

from parcel_mod_widgets.models import metadata
from parcel_mod_widgets.router import router
from parcel_sdk import Module, Permission, SidebarItem

module = Module(
    name="widgets",
    version="0.1.0",
    permissions=(
        Permission("widgets.read", "View widgets"),
        Permission("widgets.write", "Create and edit widgets"),
    ),
    capabilities=(),                                      # e.g., ("http_egress",) — admin approves at install
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=(
        SidebarItem(label="Widgets", href="/mod/widgets/", permission="widgets.read"),
    ),
)
```

```toml
# pyproject.toml
[project]
name = "parcel-mod-widgets"
dependencies = ["parcel-sdk", "fastapi>=0.115"]

[project.entry-points."parcel.modules"]
widgets = "parcel_mod_widgets:module"
```

## Writing routes — `parcel_sdk.shell_api`

Modules get DB sessions, auth, permission checks, flashes, templates, and the composed sidebar exclusively through `parcel_sdk.shell_api`. You never import `parcel_shell.*`.

```python
# router.py
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_sdk import shell_api
from parcel_sdk.shell_api import Flash

router = APIRouter(tags=["mod-widgets"])


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Any = Depends(shell_api.require_permission("widgets.read")),
    db: AsyncSession = Depends(shell_api.get_session()),
) -> Response:
    perms = await shell_api.effective_permissions(request, user)
    tpl = shell_api.get_templates()
    return tpl.TemplateResponse(
        request,
        "widgets/index.html",
        {
            "user": user,
            "sidebar": shell_api.sidebar_for(request, perms),
            "active_path": "/mod/widgets",
            "settings": request.app.state.settings,
        },
    )


@router.post("/do-something")
async def do_it(
    request: Request,
    user: Any = Depends(shell_api.require_permission("widgets.write")),
) -> Response:
    response = RedirectResponse(url="/mod/widgets/", status_code=303)
    shell_api.set_flash(response, Flash(kind="success", msg="Done."))
    return response
```

### The six facade functions

| Symbol | Use for |
|---|---|
| `shell_api.get_session()` | `db: AsyncSession = Depends(shell_api.get_session())` — one session per request, auto-commit on success. |
| `shell_api.require_permission(name)` | HTML-auth dep. Redirects to `/login?next=…` if unauthed, to `/` with an error flash if missing the permission. |
| `shell_api.effective_permissions(request, user)` | Compute the user's full permission set (for filtering sidebar items, conditional UI). |
| `shell_api.set_flash(response, flash)` | Attach a one-shot banner message to the next page view. |
| `shell_api.get_templates()` | Shared `Jinja2Templates`. Your `templates_dir` is already on the loader chain — reference templates as `"<name>/whatever.html"`. |
| `shell_api.sidebar_for(request, perms)` | Composed sidebar (shell sections + every active module's section) filtered by the user's perms, for template context. |
| `shell_api.Flash(kind, msg)` | Frozen dataclass. `kind` is `"success" \| "error" \| "info"`. |

## Models

```python
# models.py
from sqlalchemy import MetaData, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

metadata = MetaData(schema="mod_widgets")


class WidgetsBase(DeclarativeBase):
    metadata = metadata  # type: ignore[assignment]


class Widget(WidgetsBase):
    __tablename__ = "widgets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[...] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
```

Bind every table to your `metadata` so Alembic autogenerate picks up your models and nothing else.

## Migrations

Each module owns its own Alembic directory and `alembic_version` row (lives inside `mod_<name>.alembic_version`, not `public`, so downgrading past the shell baseline is safe).

```bash
# create a new revision
cd modules/widgets/src/parcel_mod_widgets
uv run alembic revision --autogenerate -m "add widget fields"

# apply (or use `uv run parcel migrate --module widgets`)
uv run alembic upgrade head
```

The scaffold's initial migration is just `CREATE SCHEMA IF NOT EXISTS "mod_widgets"`. Add your tables in subsequent revisions.

## Templates

Jinja templates live under `src/parcel_mod_<name>/templates/<name>/`. Your templates can `{% extends "_base.html" %}` — the shell's base template is already on the loader. Template context you'll typically pass:

- `user`, `sidebar`, `active_path`, `settings` (the four keys `_base.html` expects)
- Anything else your view needs.

## Testing

```python
# tests/test_smoke.py
from parcel_mod_widgets import module


def test_module_identity() -> None:
    assert module.name == "widgets"
    assert module.version == "0.1.0"
```

Integration tests can import `parcel_shell.*` freely — the SDK-only constraint applies to **runtime/library** code, not tests. The workspace-root `conftest.py` binds `shell_api` at pytest collection time so module imports that reach into `Depends(shell_api.require_permission(...))` at decoration time don't crash.

## Capabilities and the sandbox gate (Phase 7a)

As of Phase 7a, `capabilities` is a real enforcement hook when a module is installed through the sandbox pipeline (admin uploads a zip, or `parcel sandbox install <path>`). The gate runs `ruff` + `bandit` + a custom AST policy and rejects anything that imports or calls a dangerous primitive unless the manifest declares the matching capability.

**The four capability values:**

| Capability | Unlocks |
|---|---|
| `filesystem` | `import os`, `open(...)` |
| `process` | `import subprocess` |
| `network` | `socket`, `urllib`, `http.*`, `httpx`, `requests`, `aiohttp` |
| `raw_sql` | `sqlalchemy.text(...)` |

Declare them in the `Module()` manifest:

```python
module = Module(
    name="widgets",
    version="0.1.0",
    capabilities=("network",),  # module plans to make outbound HTTP calls
    ...
)
```

**Always blocked** regardless of what's declared: `import sys`, `import importlib`, anything from `parcel_shell.*`, calls to the four dynamic-code builtins (`eval`/`exec`/`compile`/`__import__`), and attribute access to sandbox-escape dunders (`__class__`, `__subclasses__`, `__globals__`, `__builtins__`, `__mro__`, `__code__`).

The gate only scans **runtime** code. Tests are allowed to import `parcel_shell.*` or call `subprocess` freely — the SDK-only constraint is a runtime rule, not a test rule.

Human-authored modules installed via `parcel install` or `POST /admin/modules/install` bypass the gate entirely (trusted input). The gate exists so that AI-generated modules — landing in Phase 7b — go through a consistent safety check before the admin sees a preview.
