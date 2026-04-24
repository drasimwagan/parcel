"""Inline string templates for ``parcel new-module``.

All templates take a single ``{name}`` placeholder (snake_case module name).
Literal ``{`` and ``}`` in the rendered output are written as ``{{``/``}}``.
"""

from __future__ import annotations

PYPROJECT = """\
[project]
name = "parcel-mod-{name}"
version = "0.1.0"
description = "Parcel module: {name}"
readme = "README.md"
requires-python = ">=3.12"
license = {{ text = "MIT" }}
dependencies = [
    "parcel-sdk",
    "fastapi>=0.115",
]

[project.entry-points."parcel.modules"]
{name} = "parcel_mod_{name}:module"

[tool.uv.sources]
parcel-sdk = {{ workspace = true }}

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parcel_mod_{name}"]
"""

README = """\
# parcel-mod-{name}

A Parcel module.
"""

ALEMBIC_INI = """\
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = .
version_path_separator = os
path_separator = os
sqlalchemy.url = postgresql+asyncpg://parcel:parcel@postgres:5432/parcel

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

ALEMBIC_ENV_PY = """\
from parcel_mod_{name} import module
from parcel_sdk.alembic_env import run_async_migrations

run_async_migrations(module)
"""

ALEMBIC_SCRIPT_MAKO = '''\
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''

INIT_MIGRATION = '''\
"""init {name}

Revision ID: 0001_init
Revises:
"""
from __future__ import annotations

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "mod_{name}"')


def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "mod_{name}" CASCADE')
'''

INIT_PY = """\
from __future__ import annotations

from pathlib import Path

from parcel_mod_{name}.models import metadata
from parcel_mod_{name}.router import router
from parcel_sdk import Module

module = Module(
    name="{name}",
    version="0.1.0",
    permissions=(),
    capabilities=(),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=(),
)

__all__ = ["module"]
"""

MODELS_PY = """\
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

metadata = MetaData(schema="mod_{name}")


class {pascal}Base(DeclarativeBase):
    metadata = metadata  # type: ignore[assignment]
"""

ROUTER_PY = """\
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from starlette.responses import HTMLResponse

from parcel_sdk import shell_api

router = APIRouter(tags=["mod-{name}"])


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Any = Depends(shell_api.require_permission("")),
) -> Response:
    # Replace the empty permission string above with a real permission once you
    # declare one in ``module.permissions``. Until then, any logged-in admin passes.
    tpl = shell_api.get_templates()
    perms = await shell_api.effective_permissions(request, user)
    return tpl.TemplateResponse(
        request,
        "{name}/index.html",
        {{
            "user": user,
            "sidebar": shell_api.sidebar_for(request, perms),
            "active_path": "/mod/{name}",
            "settings": request.app.state.settings,
        }},
    )
"""

INDEX_HTML = """\
{{% extends "_base.html" %}}
{{% block content %}}
<h1>{name}</h1>
<p>Hello from the {name} module.</p>
{{% endblock %}}
"""

TEST_SMOKE = """\
from __future__ import annotations

from parcel_mod_{name} import module


def test_module_identity() -> None:
    assert module.name == "{name}"
    assert module.version == "0.1.0"
"""
