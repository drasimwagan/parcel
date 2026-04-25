# Phase 9 — Reports + PDF Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modules declare `Report` objects on their manifest; the shell auto-mounts a parameter-form / HTML-preview / PDF-export trio per report. Contacts ships a reference `contacts.directory` report.

**Architecture:** Mirror Phase 8 dashboards. New `parcel_shell/reports/` package holds a registry, a router (3 routes per report), a Pydantic-driven form renderer, and a thin WeasyPrint wrapper. SDK gets a `Report`/`ReportContext` pair plus a new `Module.reports` tuple field. Templates live alongside the dashboards templates and are loaded through the existing `Jinja2Templates` choice loader. The shell registers its router after dashboards; per-module template dirs are already prepended by `mount_module`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Jinja2, HTMX, Tailwind (CDN), WeasyPrint 62.x, pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-04-24-phase-9-reports-design.md`](../specs/2026-04-24-phase-9-reports-design.md)

**Spec deviations to call out (resolved here):**

1. The spec sketches `from parcel_sdk.users import User` for `ReportContext.user`. The SDK has no `users` module; Phase 8's `Ctx` uses `user_id: UUID`. **Resolution:** `ReportContext` carries `user_id: UUID`, mirroring `Ctx`. Module data fns can re-fetch the User via the session if they need more than the id.
2. The spec's sidebar entries use `{module.title}: {report.title}`. `Module` has no `title` field. **Resolution:** use `f"{module.name.capitalize()}: {report.title}"`, mirroring how `composed_sections` already labels module sidebar sections.
3. Contacts is at version `0.1.0` in tree (not `0.2.0` as CLAUDE.md mentions). **Resolution:** bump straight from `0.1.0` → `0.3.0` as the spec calls for.
4. The spec writes `static_root` for WeasyPrint's `base_url`. The shell exposes static assets at `/static` mounted from `_UI_STATIC_DIR`. **Resolution:** pass the absolute file URL of `_UI_STATIC_DIR` (`Path.as_uri() + "/"`) to WeasyPrint; reports render server-side with absolute file paths so WeasyPrint can resolve any `/static/...` references on disk.

---

## File structure

### Created

| Path | Responsibility |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/reports.py` | `Report`, `ReportContext` dataclasses |
| `packages/parcel-sdk/tests/test_reports.py` | SDK unit tests for `Report` / `ReportContext` |
| `packages/parcel-shell/src/parcel_shell/reports/__init__.py` | Package marker (one-line docstring) |
| `packages/parcel-shell/src/parcel_shell/reports/registry.py` | `RegisteredReport`, `collect_reports`, `find_report` |
| `packages/parcel-shell/src/parcel_shell/reports/router.py` | The three routes per report |
| `packages/parcel-shell/src/parcel_shell/reports/forms.py` | `render_form(model, values, errors) -> str` |
| `packages/parcel-shell/src/parcel_shell/reports/pdf.py` | `html_to_pdf(html, *, base_url) -> bytes` |
| `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_form.html` | Admin-chrome wrapper for the param form |
| `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_html_chrome.html` | Admin-chrome wrapper for the rendered report |
| `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_report_base.html` | Base template module reports `{% extends %}` |
| `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_error.html` | Inline error block |
| `packages/parcel-shell/tests/test_reports_registry.py` | Registry collection / lookup tests |
| `packages/parcel-shell/tests/test_reports_forms.py` | Form auto-render unit tests |
| `packages/parcel-shell/tests/test_reports_pdf.py` | `html_to_pdf` smoke test |
| `packages/parcel-shell/tests/test_reports_routes.py` | Route auth, validation, render, pdf tests |
| `packages/parcel-shell/tests/test_reports_sidebar.py` | `_reports_section` tests |
| `packages/parcel-shell/tests/test_reports_boot_validation.py` | Boot warning when permission missing |
| `modules/contacts/src/parcel_mod_contacts/reports/__init__.py` | Package marker, exports `directory_report` |
| `modules/contacts/src/parcel_mod_contacts/reports/directory.py` | `ContactsDirectoryParams`, `directory_data`, `directory_report` |
| `modules/contacts/src/parcel_mod_contacts/templates/reports/directory.html` | Reference report template |
| `modules/contacts/tests/test_contacts_report_directory.py` | Reference-report data-fn tests |
| `docs/reports-authoring.md` | Worked-example doc |

### Modified

| Path | Change |
|---|---|
| `packages/parcel-sdk/src/parcel_sdk/__init__.py` | Re-export `Report`, `ReportContext`; bump `__version__` to `0.5.0` |
| `packages/parcel-sdk/src/parcel_sdk/module.py` | Add `reports: tuple[Report, ...] = ()` field |
| `packages/parcel-shell/pyproject.toml` | Add `weasyprint>=62,<63` runtime dep |
| `packages/parcel-shell/src/parcel_shell/app.py` | `include_router(reports_router)` after dashboards |
| `packages/parcel-shell/src/parcel_shell/ui/templates.py` | Append `_REPORTS_DIR` to the choice loader |
| `packages/parcel-shell/src/parcel_shell/ui/sidebar.py` | Add `_reports_section`; insert into `sidebar_for` after dashboards |
| `packages/parcel-shell/src/parcel_shell/modules/integration.py` | Boot-time warning if any report's permission isn't declared by the module |
| `modules/contacts/src/parcel_mod_contacts/__init__.py` | Bump version to `0.3.0`; add `reports=(directory_report,)` |
| `modules/contacts/pyproject.toml` | Bump version to `0.3.0` |
| `docker/Dockerfile` | `apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info fonts-dejavu-core` |
| `docs/module-authoring.md` | New "Reports" section |
| `CLAUDE.md` | Phase 9 status → ✅; locked-decisions Phase-9 block; current-phase paragraph; next-phase pointer to Phase 10 |

---

## Task 1: SDK — `Report` and `ReportContext` dataclasses

**Files:**
- Create: `packages/parcel-sdk/src/parcel_sdk/reports.py`
- Create: `packages/parcel-sdk/tests/test_reports.py`

- [ ] **Step 1: Write the failing test**

Create `packages/parcel-sdk/tests/test_reports.py`:

```python
from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from pydantic import BaseModel

from parcel_sdk import Report, ReportContext


class _Params(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {"hello": "world"}


def test_report_is_frozen_kw_only_dataclass() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="contacts.read",
        template="reports/directory.html",
        data=_data,
        params=_Params,
    )
    assert dataclasses.is_dataclass(r)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.title = "changed"  # type: ignore[misc]


def test_report_requires_kw_only() -> None:
    # Positional construction should raise because the dataclass is kw_only.
    with pytest.raises(TypeError):
        Report("dir", "Directory", "contacts.read", "reports/directory.html", _data)  # type: ignore[misc]


def test_report_params_optional_defaults_none() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="contacts.read",
        template="reports/directory.html",
        data=_data,
    )
    assert r.params is None
    assert r.form_template is None


def test_report_context_is_frozen() -> None:
    # Use a non-AsyncSession sentinel — ReportContext should not validate at runtime.
    ctx = ReportContext(session=object(), user_id=uuid4(), params=None)  # type: ignore[arg-type]
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.params = _Params()  # type: ignore[misc]
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
uv run pytest packages/parcel-sdk/tests/test_reports.py -v
```

Expected: ImportError on `from parcel_sdk import Report, ReportContext`.

- [ ] **Step 3: Implement the SDK module**

Create `packages/parcel-sdk/src/parcel_sdk/reports.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from pydantic import BaseModel
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ReportContext:
    """Per-request context passed to a report's data function."""

    session: AsyncSession
    user_id: UUID
    params: BaseModel | None


@dataclass(frozen=True, kw_only=True)
class Report:
    """A printable, parameterised report attached to a module manifest."""

    slug: str
    title: str
    permission: str
    template: str
    data: Callable[[ReportContext], Awaitable[dict[str, Any]]]
    params: type[BaseModel] | None = None
    form_template: str | None = None


__all__ = ["Report", "ReportContext"]
```

- [ ] **Step 4: Re-export from the SDK package and bump version**

Edit `packages/parcel-sdk/src/parcel_sdk/__init__.py`:

```python
"""Parcel SDK — the stable Python API every Parcel module imports.

Phase 9 surface: Phase 8 + reports (Report, ReportContext).
"""

from __future__ import annotations

from parcel_sdk import shell_api
from parcel_sdk.alembic_env import run_async_migrations
from parcel_sdk.dashboards import (
    BarWidget,
    Ctx,
    Dashboard,
    Dataset,
    HeadlineWidget,
    Kpi,
    KpiWidget,
    LineWidget,
    Series,
    Table,
    TableWidget,
    Widget,
    scalar_query,
    series_query,
    table_query,
)
from parcel_sdk.module import Module, Permission
from parcel_sdk.reports import Report, ReportContext
from parcel_sdk.sidebar import SidebarItem

__all__ = [
    "BarWidget",
    "Ctx",
    "Dashboard",
    "Dataset",
    "HeadlineWidget",
    "Kpi",
    "KpiWidget",
    "LineWidget",
    "Module",
    "Permission",
    "Report",
    "ReportContext",
    "Series",
    "SidebarItem",
    "Table",
    "TableWidget",
    "Widget",
    "__version__",
    "run_async_migrations",
    "scalar_query",
    "series_query",
    "shell_api",
    "table_query",
]
__version__ = "0.5.0"
```

- [ ] **Step 5: Run the test and verify it passes**

```bash
uv run pytest packages/parcel-sdk/tests/test_reports.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/reports.py \
        packages/parcel-sdk/src/parcel_sdk/__init__.py \
        packages/parcel-sdk/tests/test_reports.py
git commit -m "feat(sdk): add Report and ReportContext for phase 9"
```

---

## Task 2: SDK — `Module.reports` field

**Files:**
- Modify: `packages/parcel-sdk/src/parcel_sdk/module.py`
- Modify: `packages/parcel-sdk/tests/test_module.py`

- [ ] **Step 1: Add a failing test**

Append to `packages/parcel-sdk/tests/test_module.py`:

```python
from parcel_sdk import Module, Report, ReportContext


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def test_module_reports_defaults_to_empty_tuple() -> None:
    m = Module(name="demo", version="0.1.0")
    assert m.reports == ()


def test_module_reports_accepts_tuple_of_reports() -> None:
    r = Report(
        slug="dir",
        title="Directory",
        permission="demo.read",
        template="reports/dir.html",
        data=_data,
    )
    m = Module(name="demo", version="0.1.0", reports=(r,))
    assert m.reports == (r,)
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-sdk/tests/test_module.py -v -k reports
```

Expected: AttributeError or TypeError on `reports=` kwarg.

- [ ] **Step 3: Add the field**

Edit `packages/parcel-sdk/src/parcel_sdk/module.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter  # noqa: F401
    from sqlalchemy import MetaData  # noqa: F401

    from parcel_sdk.dashboards import Dashboard
    from parcel_sdk.reports import Report

from parcel_sdk.sidebar import SidebarItem


@dataclass(frozen=True)
class Permission:
    name: str
    description: str


@dataclass(frozen=True)
class Module:
    name: str
    version: str
    permissions: tuple[Permission, ...] = ()
    capabilities: tuple[str, ...] = ()
    alembic_ini: Path | None = None
    metadata: MetaData | None = None
    # Phase 5 additions — optional UI contribution:
    router: Any | None = None
    templates_dir: Path | None = None
    sidebar_items: tuple[SidebarItem, ...] = ()
    dashboards: tuple[Dashboard, ...] = ()
    reports: tuple[Report, ...] = ()
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-sdk/tests/test_module.py -v
```

Expected: all green, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-sdk/src/parcel_sdk/module.py packages/parcel-sdk/tests/test_module.py
git commit -m "feat(sdk): add Module.reports tuple field"
```

---

## Task 3: Shell — add WeasyPrint dependency

**Files:**
- Modify: `packages/parcel-shell/pyproject.toml`
- Modify: `docker/Dockerfile`

- [ ] **Step 1: Add WeasyPrint to shell deps**

Edit `packages/parcel-shell/pyproject.toml`. Inside the `dependencies = [...]` list, append:

```toml
    "weasyprint>=62,<63",
```

The full list should now end:

```toml
    "anthropic>=0.40,<1.0",
    "weasyprint>=62,<63",
]
```

- [ ] **Step 2: Sync the workspace**

```bash
uv sync --all-packages
```

Expected: WeasyPrint and its Python deps install. On Windows, native libs come bundled with WeasyPrint's GTK wheels. On Linux/Docker we add system libs in the next step.

- [ ] **Step 3: Add system libs to the Docker image**

Read `docker/Dockerfile` first, find the `apt-get install` block (or add one before the Python install), and ensure these packages are present (one combined `apt-get install` line):

```
libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libcairo2 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info fonts-dejavu-core
```

If the Dockerfile already has an `apt-get install` for shell deps, append these tokens. Otherwise add a new layer above the `COPY` that installs Python deps:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
        libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
        shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 4: Smoke-test the import**

```bash
uv run python -c "import weasyprint; print(weasyprint.__version__)"
```

Expected: prints `62.x` (e.g. `62.3`). If this errors on Windows with a missing native lib, follow the WeasyPrint Windows install hint — install the GTK runtime once, no further code change.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/pyproject.toml docker/Dockerfile uv.lock
git commit -m "chore(shell): add weasyprint runtime dep + docker native libs"
```

---

## Task 4: Shell — `pdf.py` helper

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/reports/__init__.py`
- Create: `packages/parcel-shell/src/parcel_shell/reports/pdf.py`
- Create: `packages/parcel-shell/tests/test_reports_pdf.py`

- [ ] **Step 1: Create the package marker**

`packages/parcel-shell/src/parcel_shell/reports/__init__.py`:

```python
"""Shell-side reports plumbing (registry, router, templates, PDF)."""
```

- [ ] **Step 2: Write the failing test**

Create `packages/parcel-shell/tests/test_reports_pdf.py`:

```python
from __future__ import annotations

from parcel_shell.reports.pdf import html_to_pdf


def test_html_to_pdf_returns_pdf_bytes() -> None:
    out = html_to_pdf(
        "<html><body><h1>Hello</h1></body></html>",
        base_url="file:///tmp/",
    )
    assert isinstance(out, bytes)
    assert out.startswith(b"%PDF-")
    assert len(out) > 100
```

- [ ] **Step 3: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_pdf.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `pdf.py`**

`packages/parcel-shell/src/parcel_shell/reports/pdf.py`:

```python
from __future__ import annotations

import weasyprint


def html_to_pdf(html: str, *, base_url: str) -> bytes:
    """Render an HTML string to PDF bytes using WeasyPrint.

    `base_url` resolves any relative `<img src>`, `<link href>`, etc. inside
    the HTML. Pass a `file://` URI when assets are on disk.
    """
    return weasyprint.HTML(string=html, base_url=base_url).write_pdf()
```

- [ ] **Step 5: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_pdf.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/reports/__init__.py \
        packages/parcel-shell/src/parcel_shell/reports/pdf.py \
        packages/parcel-shell/tests/test_reports_pdf.py
git commit -m "feat(shell): add reports.pdf html_to_pdf helper"
```

---

## Task 5: Shell — form auto-renderer (str/int/float/bool)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/reports/forms.py`
- Create: `packages/parcel-shell/tests/test_reports_forms.py`

- [ ] **Step 1: Write the failing tests**

Create `packages/parcel-shell/tests/test_reports_forms.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

from parcel_shell.reports.forms import render_form


class StrParams(BaseModel):
    q: str | None = None


class IntParams(BaseModel):
    n: int = 0


class FloatParams(BaseModel):
    f: float = 1.0


class BoolParams(BaseModel):
    on: bool = False


class DescribedParams(BaseModel):
    q: str | None = Field(default=None, description="Search by name")


def test_render_form_str_input() -> None:
    html = render_form(StrParams, values={}, errors={})
    assert "<form" in html
    assert 'name="q"' in html
    assert 'type="text"' in html


def test_render_form_int_input() -> None:
    html = render_form(IntParams, values={}, errors={})
    assert 'name="n"' in html
    assert 'type="number"' in html


def test_render_form_float_input() -> None:
    html = render_form(FloatParams, values={}, errors={})
    assert 'name="f"' in html
    assert 'type="number"' in html
    assert 'step="any"' in html


def test_render_form_bool_input() -> None:
    html = render_form(BoolParams, values={}, errors={})
    assert 'name="on"' in html
    assert 'type="checkbox"' in html


def test_render_form_optional_drops_required() -> None:
    html = render_form(StrParams, values={}, errors={})
    # Optional[str] -> required not present on the input.
    # Locate the q input only:
    snippet = html[html.index('name="q"') :]
    snippet = snippet[: snippet.index(">") + 1]
    assert "required" not in snippet


def test_render_form_description_renders_helper() -> None:
    html = render_form(DescribedParams, values={}, errors={})
    assert "Search by name" in html


def test_render_form_value_prefilled() -> None:
    html = render_form(StrParams, values={"q": "alice"}, errors={})
    assert 'value="alice"' in html


def test_render_form_errors_rendered_inline() -> None:
    html = render_form(IntParams, values={"n": "abc"}, errors={"n": ["must be a number"]})
    assert "must be a number" in html
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_forms.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement minimum to pass these tests**

Create `packages/parcel-shell/src/parcel_shell/reports/forms.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from html import escape
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _is_optional(annotation: Any) -> tuple[bool, Any]:
    """Return (is_optional, inner_type) for `T | None` / `Optional[T]`."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1 and len(get_args(annotation)) > 1:
            return True, args[0]
    return False, annotation


def _input_attrs(name: str, *, required: bool, value: Any, kind: str) -> str:
    parts = [f'name="{escape(name)}"', f'type="{kind}"']
    if required:
        parts.append("required")
    if kind == "checkbox":
        if value:
            parts.append("checked")
    elif value is not None and value != "":
        parts.append(f'value="{escape(str(value))}"')
    if kind == "number":
        # Float fields advertise step="any"; ints leave the default.
        pass
    return " ".join(parts)


def _control_for(
    name: str,
    annotation: Any,
    field: FieldInfo,
    values: dict[str, Any],
    *,
    is_optional: bool,
) -> str:
    extras = field.json_schema_extra or {}
    widget = extras.get("widget") if isinstance(extras, dict) else None
    required = not is_optional and field.is_required()
    raw_value = values.get(name, field.default if field.default is not None else "")

    if widget == "textarea":
        return (
            f'<textarea name="{escape(name)}" '
            f'class="w-full rounded border-gray-300 p-2"'
            f'{" required" if required else ""}>'
            f"{escape(str(raw_value or ''))}</textarea>"
        )

    if annotation is bool:
        return (
            f'<input {_input_attrs(name, required=False, value=bool(raw_value), kind="checkbox")} '
            'class="rounded border-gray-300">'
        )

    if annotation is int:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="number")} '
            'step="1" class="w-full rounded border-gray-300">'
        )

    if annotation is float:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="number")} '
            'step="any" class="w-full rounded border-gray-300">'
        )

    if annotation is date:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="date")} '
            'class="w-full rounded border-gray-300">'
        )

    if annotation is datetime:
        return (
            f'<input {_input_attrs(name, required=required, value=raw_value, kind="datetime-local")} '
            'class="w-full rounded border-gray-300">'
        )

    origin = get_origin(annotation)
    if origin is Literal:
        opts = []
        for choice in get_args(annotation):
            sel = " selected" if str(raw_value) == str(choice) else ""
            opts.append(f'<option value="{escape(str(choice))}"{sel}>{escape(str(choice))}</option>')
        return (
            f'<select name="{escape(name)}" class="w-full rounded border-gray-300"'
            f'{" required" if required else ""}>{"".join(opts)}</select>'
        )

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        opts = []
        for member in annotation:
            sel = " selected" if str(raw_value) == str(member.value) else ""
            opts.append(
                f'<option value="{escape(str(member.value))}"{sel}>{escape(member.name)}</option>'
            )
        return (
            f'<select name="{escape(name)}" class="w-full rounded border-gray-300"'
            f'{" required" if required else ""}>{"".join(opts)}</select>'
        )

    # Default: text input.
    return (
        f'<input {_input_attrs(name, required=required, value=raw_value, kind="text")} '
        'class="w-full rounded border-gray-300">'
    )


def render_form(
    model: type[BaseModel],
    values: dict[str, Any],
    errors: dict[str, list[str]],
) -> str:
    """Render a Tailwind-styled HTML <form> from a Pydantic model.

    `values` pre-fills the inputs (used when re-rendering after a validation
    error). `errors` is `{field_name: [messages, ...]}` from
    `ValidationError.errors()`.
    """
    rows: list[str] = []
    for name, field in model.model_fields.items():
        is_opt, inner = _is_optional(field.annotation)
        control = _control_for(name, inner, field, values, is_optional=is_opt)
        label = field.title or name.replace("_", " ").capitalize()
        helper = ""
        if field.description:
            helper = (
                f'<p class="text-xs text-gray-500 mt-1">{escape(field.description)}</p>'
            )
        err_html = ""
        if name in errors and errors[name]:
            joined = "; ".join(errors[name])
            err_html = f'<p class="text-xs text-red-600 mt-1">{escape(joined)}</p>'
        rows.append(
            f'<div class="mb-3">'
            f'<label class="block text-sm font-medium text-gray-700 mb-1">{escape(label)}</label>'
            f"{control}{helper}{err_html}"
            "</div>"
        )
    return '<form class="space-y-2">' + "".join(rows) + "</form>"
```

- [ ] **Step 4: Run and verify the str/int/float/bool/optional/desc/value/errors tests pass**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_forms.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/reports/forms.py \
        packages/parcel-shell/tests/test_reports_forms.py
git commit -m "feat(shell): add reports form auto-renderer (basic types)"
```

---

## Task 6: Form auto-renderer — date / datetime / Literal / Enum / textarea

**Files:**
- Modify: `packages/parcel-shell/tests/test_reports_forms.py`

- [ ] **Step 1: Add failing tests for the remaining types**

Append to `packages/parcel-shell/tests/test_reports_forms.py`:

```python
from datetime import date, datetime
from enum import Enum
from typing import Literal


class DateParams(BaseModel):
    d: date | None = None


class DateTimeParams(BaseModel):
    when: datetime | None = None


class LiteralParams(BaseModel):
    mode: Literal["draft", "final"] = "draft"


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"


class EnumParams(BaseModel):
    c: Color = Color.RED


class TextareaParams(BaseModel):
    notes: str | None = Field(default=None, json_schema_extra={"widget": "textarea"})


def test_render_form_date_input() -> None:
    html = render_form(DateParams, values={}, errors={})
    assert 'type="date"' in html


def test_render_form_datetime_input() -> None:
    html = render_form(DateTimeParams, values={}, errors={})
    assert 'type="datetime-local"' in html


def test_render_form_literal_select() -> None:
    html = render_form(LiteralParams, values={}, errors={})
    assert "<select" in html
    assert 'value="draft"' in html
    assert 'value="final"' in html


def test_render_form_enum_select() -> None:
    html = render_form(EnumParams, values={}, errors={})
    assert "<select" in html
    assert 'value="red"' in html
    assert 'value="blue"' in html


def test_render_form_textarea_widget() -> None:
    html = render_form(TextareaParams, values={}, errors={})
    assert "<textarea" in html
    assert 'name="notes"' in html
```

- [ ] **Step 2: Run and verify they pass (the implementation already covers them)**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_forms.py -v
```

Expected: 13 passed total.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/test_reports_forms.py
git commit -m "test(shell): cover date/datetime/literal/enum/textarea form widgets"
```

---

## Task 7: Templates — base, html-chrome, form, error

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_report_base.html`
- Create: `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_html_chrome.html`
- Create: `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_form.html`
- Create: `packages/parcel-shell/src/parcel_shell/reports/templates/reports/_error.html`
- Modify: `packages/parcel-shell/src/parcel_shell/ui/templates.py`

- [ ] **Step 1: Write `_report_base.html`**

`packages/parcel-shell/src/parcel_shell/reports/templates/reports/_report_base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ report.title }}</title>
  <style>
    @page {
      size: A4 portrait;
      margin: 20mm;
      @top-center { content: "{{ report.title }}"; font-size: 9pt; color: #666; }
      @bottom-right { content: "Page " counter(page) " / " counter(pages); font-size: 9pt; color: #666; }
    }
    body { font-family: -apple-system, "Segoe UI", sans-serif; font-size: 10pt; color: #111; }
    h1 { font-size: 16pt; margin: 0 0 4pt; }
    .meta { font-size: 9pt; color: #666; margin-bottom: 12pt; }
    table { width: 100%; border-collapse: collapse; margin-top: 8pt; }
    th, td { text-align: left; padding: 4pt 6pt; border-bottom: 1px solid #ddd; vertical-align: top; }
    th { background: #f5f5f5; font-weight: 600; }
    {% block page_css %}{% endblock %}
  </style>
</head>
<body>
  <header>
    <h1>{{ report.title }}</h1>
    <div class="meta">
      Generated {{ generated_at.strftime("%Y-%m-%d %H:%M") }}
      {%- if param_summary %} &middot; {{ param_summary }}{% endif %}
    </div>
  </header>
  {% block content %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Write `_html_chrome.html`**

`packages/parcel-shell/src/parcel_shell/reports/templates/reports/_html_chrome.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ report.title }}{% endblock %}
{% block content %}
<div class="mb-4 flex items-center justify-between">
  <div>
    <h1 class="text-xl font-semibold">{{ report.title }}</h1>
    <p class="text-sm text-gray-500">{{ module_name|capitalize }} report</p>
  </div>
  <div class="flex gap-2">
    <a href="/reports/{{ module_name }}/{{ report.slug }}{% if report.params %}?{{ querystring }}{% endif %}"
       class="px-3 py-1 text-sm rounded border border-gray-300 hover:bg-gray-50">Edit filters</a>
    <a href="/reports/{{ module_name }}/{{ report.slug }}/pdf{% if querystring %}?{{ querystring }}{% endif %}"
       class="px-3 py-1 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700">Download PDF</a>
  </div>
</div>
<div id="report-content" class="bg-white rounded shadow p-6">
  {{ report_html|safe }}
</div>
{% endblock %}
```

- [ ] **Step 3: Write `_form.html`**

`packages/parcel-shell/src/parcel_shell/reports/templates/reports/_form.html`:

```html
{% extends "_base.html" %}
{% block title %}{{ report.title }}{% endblock %}
{% block content %}
<div class="mb-4">
  <h1 class="text-xl font-semibold">{{ report.title }}</h1>
  <p class="text-sm text-gray-500">{{ module_name|capitalize }} report</p>
</div>
<div class="bg-white rounded shadow p-6 max-w-xl">
  <form method="get" action="/reports/{{ module_name }}/{{ report.slug }}/render"
        hx-get="/reports/{{ module_name }}/{{ report.slug }}/render"
        hx-target="#report-content" hx-push-url="true">
    {{ form_html|safe }}
    <div class="mt-4 flex gap-2">
      <button type="submit" class="px-3 py-1 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700">
        Run report
      </button>
    </div>
  </form>
  <div id="report-content"></div>
</div>
{% endblock %}
```

- [ ] **Step 4: Write `_error.html`**

`packages/parcel-shell/src/parcel_shell/reports/templates/reports/_error.html`:

```html
<div class="bg-red-50 border border-red-200 rounded p-4 text-sm text-red-700">
  <strong>Could not render this report.</strong>
  <p class="mt-1">{{ message }}</p>
</div>
```

- [ ] **Step 5: Wire the templates dir into the choice loader**

Edit `packages/parcel-shell/src/parcel_shell/ui/templates.py`:

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import jinja2
from fastapi.templating import Jinja2Templates

_SHELL_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DASHBOARDS_DIR = Path(__file__).resolve().parents[1] / "dashboards" / "templates"
_REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports" / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Shell-only Jinja2Templates. Module templates are mounted dynamically via
    :func:`add_template_dir`, which mutates the underlying loader search path.
    """
    tpl = Jinja2Templates(directory=str(_SHELL_TEMPLATES_DIR))
    tpl.env.loader = jinja2.ChoiceLoader(
        [
            jinja2.FileSystemLoader(str(_SHELL_TEMPLATES_DIR)),
            jinja2.FileSystemLoader(str(_DASHBOARDS_DIR)),
            jinja2.FileSystemLoader(str(_REPORTS_DIR)),
        ]
    )
    from parcel_shell.ui.sidebar import active_href

    tpl.env.globals["active_href"] = active_href
    return tpl


def add_template_dir(directory: Path) -> None:
    """Prepend ``directory`` to the Jinja loader chain, if not already present."""
    tpl = get_templates()
    loader = tpl.env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    as_str = str(directory)
    for existing in loader.loaders:
        if isinstance(existing, jinja2.FileSystemLoader) and as_str in existing.searchpath:
            return
    loader.loaders = [jinja2.FileSystemLoader(as_str), *loader.loaders]
```

- [ ] **Step 6: Verify Jinja resolves the templates**

```bash
uv run python -c "from parcel_shell.ui.templates import get_templates; t = get_templates(); print(t.env.loader.list_templates())" | head -20
```

Expected: list includes `reports/_report_base.html`, `reports/_form.html`, `reports/_html_chrome.html`, `reports/_error.html`.

- [ ] **Step 7: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/reports/templates/ \
        packages/parcel-shell/src/parcel_shell/ui/templates.py
git commit -m "feat(shell): add report templates and load them in jinja"
```

---

## Task 8: Shell — registry (collect + find)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/reports/registry.py`
- Create: `packages/parcel-shell/tests/test_reports_registry.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_reports_registry.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.reports.registry import collect_reports, find_report


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def _report(slug: str = "dir") -> Report:
    return Report(
        slug=slug,
        title="Directory",
        permission="contacts.read",
        template="reports/dir.html",
        data=_data,
        params=_P,
    )


def _app(manifest: dict[str, Module]):
    return SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))


def test_collect_reports_orders_by_module_then_declaration() -> None:
    contacts = Module(name="contacts", version="0.1.0", reports=(_report("a"), _report("b")))
    sales = Module(name="sales", version="0.1.0", reports=(_report("c"),))
    out = collect_reports(_app({"sales": sales, "contacts": contacts}))
    assert [(r.module_name, r.report.slug) for r in out] == [
        ("contacts", "a"),
        ("contacts", "b"),
        ("sales", "c"),
    ]


def test_collect_reports_empty_when_no_state() -> None:
    out = collect_reports(SimpleNamespace(state=SimpleNamespace()))
    assert out == []


def test_find_report_returns_match() -> None:
    contacts = Module(name="contacts", version="0.1.0", reports=(_report("a"),))
    registered = collect_reports(_app({"contacts": contacts}))
    hit = find_report(registered, "contacts", "a")
    assert hit is not None
    assert hit.report.slug == "a"


def test_find_report_returns_none_for_missing() -> None:
    registered = collect_reports(_app({}))
    assert find_report(registered, "contacts", "a") is None
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_registry.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the registry**

`packages/parcel-shell/src/parcel_shell/reports/registry.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from parcel_sdk import Module, Report


@dataclass(frozen=True)
class RegisteredReport:
    module_name: str
    report: Report


def collect_reports(app) -> list[RegisteredReport]:
    """Walk active modules' manifests and return their reports in stable order.

    Reads ``app.state.active_modules_manifest`` (populated by ``mount_module``).
    Returns ``[]`` if state hasn't been populated yet.
    """
    manifests: dict[str, Module] = getattr(app.state, "active_modules_manifest", {})
    out: list[RegisteredReport] = []
    for name in sorted(manifests):
        module = manifests[name]
        for report in module.reports:
            out.append(RegisteredReport(module_name=name, report=report))
    return out


def find_report(
    registered: list[RegisteredReport], module_name: str, slug: str
) -> RegisteredReport | None:
    for r in registered:
        if r.module_name == module_name and r.report.slug == slug:
            return r
    return None
```

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_registry.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/reports/registry.py \
        packages/parcel-shell/tests/test_reports_registry.py
git commit -m "feat(shell): add reports registry (collect + find)"
```

---

## Task 9: Shell — router (form + render + pdf)

**Files:**
- Create: `packages/parcel-shell/src/parcel_shell/reports/router.py`
- Create: `packages/parcel-shell/tests/test_reports_routes.py`
- Modify: `packages/parcel-shell/src/parcel_shell/app.py`

- [ ] **Step 1: Sketch the router**

`packages/parcel-shell/src/parcel_shell/reports/router.py`:

```python
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse, StreamingResponse

from parcel_sdk import ReportContext
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.reports.forms import render_form
from parcel_shell.reports.pdf import html_to_pdf
from parcel_shell.reports.registry import collect_reports, find_report
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

_log = structlog.get_logger("parcel_shell.reports")
_STATIC_DIR = Path(__file__).resolve().parents[1] / "ui" / "static"
_BASE_URL = _STATIC_DIR.parent.as_uri() + "/"

router = APIRouter(prefix="/reports", tags=["reports"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not found")


def _query_dict(request: Request) -> dict[str, object]:
    raw = dict(request.query_params)
    return {k: (v if v != "" else None) for k, v in raw.items()}


def _validate_params(
    model: type[BaseModel] | None, request: Request
) -> tuple[BaseModel | None, dict[str, list[str]]]:
    if model is None:
        return None, {}
    try:
        instance = model.model_validate(_query_dict(request))
        return instance, {}
    except ValidationError as exc:
        errors: dict[str, list[str]] = {}
        for err in exc.errors():
            loc = err["loc"][0] if err["loc"] else ""
            errors.setdefault(str(loc), []).append(err["msg"])
        return None, errors


def _summary(params: BaseModel | None) -> str:
    if params is None:
        return ""
    bits: list[str] = []
    for k, v in params.model_dump().items():
        if v is None or v == "":
            continue
        bits.append(f"{k}={v}")
    return "; ".join(bits)


@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def report_form(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_reports(request.app)
    hit = find_report(registered, module_name, slug)
    if hit is None or hit.report.permission not in perms:
        raise _not_found()

    if hit.report.params is None:
        return RedirectResponse(
            f"/reports/{module_name}/{slug}/render", status_code=303
        )

    values = _query_dict(request)
    _, errors = _validate_params(hit.report.params, request)
    if hit.report.form_template is not None:
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            hit.report.form_template,
            {
                "user": user,
                "sidebar": sidebar_for(request, perms),
                "active_path": "/reports",
                "settings": request.app.state.settings,
                "permissions": perms,
                "module_name": module_name,
                "report": hit.report,
                "values": values,
                "errors": errors,
                "model": hit.report.params,
            },
        )
    form_html = render_form(hit.report.params, values, errors)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "reports/_form.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/reports",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "report": hit.report,
            "form_html": form_html,
        },
    )


async def _render_html_body(
    *, request: Request, hit, params: BaseModel | None, db: AsyncSession
) -> str:
    """Render the report's <body> contents (the template extending _report_base)."""
    ctx = ReportContext(session=db, user_id=request.state.user.id, params=params)
    data = await hit.report.data(ctx)
    templates = get_templates()
    template = templates.env.get_template(hit.report.template)
    return template.render(
        report=hit.report,
        generated_at=datetime.utcnow(),
        param_summary=data.get("param_summary") or _summary(params),
        **data,
    )


@router.get("/{module_name}/{slug}/render", response_class=HTMLResponse)
async def report_render(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_reports(request.app)
    hit = find_report(registered, module_name, slug)
    if hit is None or hit.report.permission not in perms:
        raise _not_found()

    params, errors = _validate_params(hit.report.params, request)
    if errors:
        form_html = render_form(
            hit.report.params, _query_dict(request), errors
        ) if hit.report.params is not None else ""
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "reports/_form.html",
            {
                "user": user,
                "sidebar": sidebar_for(request, perms),
                "active_path": "/reports",
                "settings": request.app.state.settings,
                "permissions": perms,
                "module_name": module_name,
                "report": hit.report,
                "form_html": form_html,
            },
        )

    request.state.user = user
    try:
        report_html = await _render_html_body(
            request=request, hit=hit, params=params, db=db
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "reports.render_failed",
            module=module_name,
            slug=slug,
            error=str(exc),
        )
        templates = get_templates()
        body = templates.env.get_template("reports/_error.html").render(
            message="The report could not be rendered."
        )
        report_html = body

    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "reports/_html_chrome.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/reports",
            "settings": request.app.state.settings,
            "permissions": perms,
            "module_name": module_name,
            "report": hit.report,
            "querystring": urlencode(
                {k: v for k, v in dict(request.query_params).items() if v}
            ),
            "report_html": report_html,
        },
    )


@router.get("/{module_name}/{slug}/pdf")
async def report_pdf(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_reports(request.app)
    hit = find_report(registered, module_name, slug)
    if hit is None or hit.report.permission not in perms:
        raise _not_found()

    params, errors = _validate_params(hit.report.params, request)
    if errors:
        # Same UX as the render route — bounce the user back to the form.
        target = f"/reports/{module_name}/{slug}"
        if request.query_params:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(target, status_code=303)

    request.state.user = user
    try:
        body = await _render_html_body(
            request=request, hit=hit, params=params, db=db
        )
        pdf = html_to_pdf(body, base_url=_BASE_URL)
    except Exception as exc:  # noqa: BLE001
        _log.exception(
            "reports.pdf_failed",
            module=module_name,
            slug=slug,
            error=str(exc),
        )
        response = RedirectResponse(f"/reports/{module_name}/{slug}", status_code=303)
        set_flash(
            response,
            ("error", "Could not generate the PDF. Please try again."),
            secret=request.app.state.settings.session_secret,
        )
        return response

    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    filename = f"{module_name}-{slug}-{stamp}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

(Note: this file imports `set_flash`. Inspect `parcel_shell/ui/dependencies.py` to confirm the signature. If `set_flash` takes only `(response, kind, message, secret)`, swap the call accordingly. Match the existing call sites in [`parcel_shell/ui/`](../../packages/parcel-shell/src/parcel_shell/ui/).)

- [ ] **Step 2: Wire the router into `create_app`**

Edit `packages/parcel-shell/src/parcel_shell/app.py`. After the existing dashboards include:

```python
    from parcel_shell.dashboards.router import router as dashboards_router

    app.include_router(dashboards_router)

    from parcel_shell.reports.router import router as reports_router

    app.include_router(reports_router)
```

- [ ] **Step 3: Write the failing route tests**

`packages/parcel-shell/tests/test_reports_routes.py`:

```python
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module

pytestmark = pytest.mark.asyncio


class _Params(BaseModel):
    q: str | None = None
    n: int = 0


async def _data_ok(ctx: ReportContext) -> dict[str, Any]:
    return {"items": ["alpha", "beta"], "param_summary": f"q={ctx.params.q}"}


async def _data_boom(_ctx: ReportContext) -> dict[str, Any]:
    raise RuntimeError("data fn exploded")


async def _data_no_params(_ctx: ReportContext) -> dict[str, Any]:
    return {"items": []}


def _module(report: Report) -> Module:
    return Module(name="demo", version="0.1.0", reports=(report,))


_REPORT_OK = Report(
    slug="dir",
    title="Demo report",
    permission="users.read",  # admin already has this
    template="reports/_demo.html",
    data=_data_ok,
    params=_Params,
)

_REPORT_GATED = Report(
    slug="dir",
    title="Demo report",
    permission="nobody.has.this",
    template="reports/_demo.html",
    data=_data_ok,
    params=_Params,
)

_REPORT_BOOM = Report(
    slug="dir",
    title="Demo report",
    permission="users.read",
    template="reports/_demo.html",
    data=_data_boom,
    params=_Params,
)

_REPORT_NO_PARAMS = Report(
    slug="np",
    title="No-params report",
    permission="users.read",
    template="reports/_demo.html",
    data=_data_no_params,
)


def _mount(app: FastAPI, report: Report) -> None:
    mount_module(
        app,
        DiscoveredModule(
            module=_module(report),
            distribution_name="parcel-mod-demo",
            distribution_version="0.1.0",
        ),
    )


# A tiny module template that extends _report_base.html.
def _ensure_demo_template(app: FastAPI) -> None:
    """Inject a demo template into the loader at runtime so tests don't need a real package."""
    import jinja2

    from parcel_shell.ui.templates import get_templates

    tpl = get_templates()
    loader = tpl.env.loader
    assert isinstance(loader, jinja2.ChoiceLoader)
    loader.loaders.insert(
        0,
        jinja2.DictLoader(
            {
                "reports/_demo.html": (
                    "{% extends 'reports/_report_base.html' %}"
                    "{% block content %}<ul>"
                    "{% for it in items %}<li>{{ it }}</li>{% endfor %}"
                    "</ul>{% endblock %}"
                )
            }
        ),
    )


@pytest_asyncio.fixture()
async def authed_with_demo_report(app: FastAPI, authed_client: AsyncClient):
    _mount(app, _REPORT_OK)
    _ensure_demo_template(app)
    return authed_client


async def test_report_form_logged_out_redirects(client: AsyncClient, app: FastAPI) -> None:
    _mount(app, _REPORT_OK)
    r = await client.get("/reports/demo/dir", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_report_form_missing_permission_returns_404(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _REPORT_GATED)
    r = await authed_client.get("/reports/demo/dir")
    assert r.status_code == 404


async def test_report_form_unknown_returns_404(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/reports/nope/none")
    assert r.status_code == 404


async def test_report_form_no_params_redirects_to_render(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _REPORT_NO_PARAMS)
    _ensure_demo_template(app)
    r = await authed_client.get("/reports/demo/np", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].endswith("/reports/demo/np/render")


async def test_report_form_renders(authed_with_demo_report: AsyncClient) -> None:
    r = await authed_with_demo_report.get("/reports/demo/dir")
    assert r.status_code == 200
    assert "Demo report" in r.text
    assert 'name="q"' in r.text


async def test_report_render_validation_error_shows_form(
    authed_with_demo_report: AsyncClient,
) -> None:
    r = await authed_with_demo_report.get("/reports/demo/dir/render?n=notanumber")
    assert r.status_code == 200
    # Form is re-rendered with the error message visible.
    assert 'name="n"' in r.text


async def test_report_render_success(authed_with_demo_report: AsyncClient) -> None:
    r = await authed_with_demo_report.get("/reports/demo/dir/render?q=alice")
    assert r.status_code == 200
    assert "alpha" in r.text and "beta" in r.text
    # Admin chrome wraps the report.
    assert 'id="report-content"' in r.text


async def test_report_render_failure_shows_error_block(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _REPORT_BOOM)
    _ensure_demo_template(app)
    r = await authed_client.get("/reports/demo/dir/render?q=x")
    assert r.status_code == 200
    assert "could not be rendered" in r.text.lower()


async def test_report_pdf_returns_pdf_bytes(authed_with_demo_report: AsyncClient) -> None:
    r = await authed_with_demo_report.get("/reports/demo/dir/pdf?q=alice")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert "attachment" in r.headers["content-disposition"]
    assert "demo-dir-" in r.headers["content-disposition"]


async def test_report_pdf_validation_error_redirects_to_form(
    authed_with_demo_report: AsyncClient,
) -> None:
    r = await authed_with_demo_report.get(
        "/reports/demo/dir/pdf?n=notanumber", follow_redirects=False
    )
    assert r.status_code == 303
    assert "/reports/demo/dir" in r.headers["location"]


async def test_report_pdf_failure_redirects_with_flash(
    app: FastAPI, authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mount(app, _REPORT_OK)
    _ensure_demo_template(app)

    def _boom(_html: str, *, base_url: str) -> bytes:
        raise RuntimeError("pdf engine off")

    monkeypatch.setattr("parcel_shell.reports.router.html_to_pdf", _boom)
    r = await authed_client.get("/reports/demo/dir/pdf?q=alice", follow_redirects=False)
    assert r.status_code == 303
    assert "/reports/demo/dir" in r.headers["location"]
```

- [ ] **Step 4: Run the route tests**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_routes.py -v
```

Expected: all green. If any step inside `_render_html_body` mismatches the actual `set_flash` signature, fix that one call (look at `parcel_shell/ui/dependencies.py` for the canonical signature) and re-run.

- [ ] **Step 5: Quick full-suite spot check**

```bash
uv run pytest packages/parcel-shell/tests/ -x -q
```

Expected: green. The new router is unconditionally mounted but won't trip existing tests because no module declares reports yet.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/reports/router.py \
        packages/parcel-shell/src/parcel_shell/app.py \
        packages/parcel-shell/tests/test_reports_routes.py
git commit -m "feat(shell): mount /reports/<module>/<slug>/{form,render,pdf}"
```

---

## Task 10: Sidebar — `_reports_section`

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`
- Create: `packages/parcel-shell/tests/test_reports_sidebar.py`

- [ ] **Step 1: Write the failing tests**

`packages/parcel-shell/tests/test_reports_sidebar.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.ui.sidebar import _reports_section


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def _report(slug: str, title: str, perm: str) -> Report:
    return Report(
        slug=slug,
        title=title,
        permission=perm,
        template="reports/x.html",
        data=_data,
        params=_P,
    )


def _request(manifest: dict[str, Module]):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest)))


def test_reports_section_visible_with_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(_report("dir", "Directory", "contacts.read"),),
    )
    section = _reports_section(_request({"contacts": contacts}), {"contacts.read"})
    assert section is not None
    assert section.label == "Reports"
    labels = [item.label for item in section.items]
    assert labels == ["Contacts: Directory"]


def test_reports_section_hidden_without_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(_report("dir", "Directory", "contacts.read"),),
    )
    section = _reports_section(_request({"contacts": contacts}), set())
    assert section is None


def test_reports_section_hidden_when_no_reports() -> None:
    contacts = Module(name="contacts", version="0.1.0")
    section = _reports_section(_request({"contacts": contacts}), {"users.read"})
    assert section is None


def test_reports_section_filters_per_report_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(
            _report("dir", "Directory", "contacts.read"),
            _report("priv", "Private", "secret.read"),
        ),
    )
    section = _reports_section(_request({"contacts": contacts}), {"contacts.read"})
    assert section is not None
    assert [i.label for i in section.items] == ["Contacts: Directory"]
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_sidebar.py -v
```

Expected: ImportError on `_reports_section`.

- [ ] **Step 3: Implement `_reports_section` and wire it into `sidebar_for`**

Edit `packages/parcel-shell/src/parcel_shell/ui/sidebar.py`. Add the new helper after `_dashboards_section`:

```python
def _reports_section(request, perms: set[str]) -> SidebarSection | None:
    """Return a sidebar section listing every visible report.

    Mirrors ``_dashboards_section`` but emits one item per report (rather than
    a single "Reports" link), as Phase 9's spec calls for.
    """
    manifest = getattr(request.app.state, "active_modules_manifest", {}) or {}
    items: list[SidebarItem] = []
    for module_name in sorted(manifest):
        module = manifest[module_name]
        for report in getattr(module, "reports", ()):
            if report.permission in perms:
                items.append(
                    SidebarItem(
                        label=f"{module_name.capitalize()}: {report.title}",
                        href=f"/reports/{module_name}/{report.slug}",
                        permission=None,
                    )
                )
    if not items:
        return None
    return SidebarSection(label="Reports", items=tuple(items))
```

And modify `sidebar_for` to insert it after the dashboards section:

```python
def sidebar_for(request, perms: set[str]) -> list[SidebarSection]:
    """Convenience: compose the sidebar using the live app state."""
    module_sections = getattr(request.app.state, "active_modules_sidebar", None)
    out = composed_sections(perms, module_sections)
    dash = _dashboards_section(request, perms)
    insert_at = 1 if out and out[0].label == "Overview" else 0
    if dash is not None:
        out.insert(insert_at, dash)
        insert_at += 1
    rep = _reports_section(request, perms)
    if rep is not None:
        out.insert(insert_at, rep)
    return out
```

Also add `"_reports_section"` to the `__all__` tuple at the top of the file.

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_sidebar.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Re-run the full sidebar/UI test suite to confirm no regressions**

```bash
uv run pytest packages/parcel-shell/tests/test_sdk_sidebar.py \
              packages/parcel-shell/tests/test_sidebar_active.py \
              packages/parcel-shell/tests/test_ui_layout.py -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ui/sidebar.py \
        packages/parcel-shell/tests/test_reports_sidebar.py
git commit -m "feat(shell): inject Reports sidebar section per visible report"
```

---

## Task 11: Boot-time validation warning

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/modules/integration.py`
- Create: `packages/parcel-shell/tests/test_reports_boot_validation.py`

- [ ] **Step 1: Write the failing test**

`packages/parcel-shell/tests/test_reports_boot_validation.py`:

```python
from __future__ import annotations

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

from parcel_sdk import Module, Permission, Report, ReportContext
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def test_mount_warns_when_report_permission_not_declared() -> None:
    app = FastAPI()
    log_events: list[dict] = []

    def _capture(_logger, _name, event_dict):
        log_events.append(event_dict)
        return event_dict

    structlog.configure(processors=[_capture])

    bad = Report(
        slug="dir",
        title="Directory",
        permission="contacts.write",  # NOT in module.permissions
        template="reports/x.html",
        data=_data,
        params=_P,
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        reports=(bad,),
    )
    mount_module(
        app,
        DiscoveredModule(
            module=module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        ),
    )

    assert any(
        e.get("event") == "module.report.unknown_permission"
        and e.get("permission") == "contacts.write"
        for e in log_events
    ), log_events
```

- [ ] **Step 2: Run and verify failure**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_boot_validation.py -v
```

Expected: assertion fails — no warning emitted yet.

- [ ] **Step 3: Add the warning inside `mount_module`**

Edit `packages/parcel-shell/src/parcel_shell/modules/integration.py`. Inside `mount_module`, after the existing state mutation (`app.state.active_modules.add(name)` and friends), add:

```python
    declared = {p.name for p in discovered.module.permissions}
    for report in getattr(discovered.module, "reports", ()):
        if report.permission not in declared:
            _log.warning(
                "module.report.unknown_permission",
                module=name,
                slug=report.slug,
                permission=report.permission,
            )
```

(`_log` is already defined at module top.)

- [ ] **Step 4: Run and verify pass**

```bash
uv run pytest packages/parcel-shell/tests/test_reports_boot_validation.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Re-run module integration tests**

```bash
uv run pytest packages/parcel-shell/tests/test_module_integration.py -v
```

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/modules/integration.py \
        packages/parcel-shell/tests/test_reports_boot_validation.py
git commit -m "feat(shell): warn at mount when a report's permission isn't declared"
```

---

## Task 12: Contacts — `directory_data` and tests

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/reports/__init__.py`
- Create: `modules/contacts/src/parcel_mod_contacts/reports/directory.py`
- Create: `modules/contacts/tests/test_contacts_report_directory.py`

- [ ] **Step 1: Sanity-check the Contacts model**

```bash
uv run python -c "from parcel_mod_contacts.models import Contact; print([c.name for c in Contact.__table__.columns])"
```

Note the column names. The plan assumes `name`, `email`, `phone`, `company`, `created_at`. If a column is named differently (e.g. `display_name`), adjust the data-fn accordingly throughout this task.

- [ ] **Step 2: Write the failing test**

`modules/contacts/tests/test_contacts_report_directory.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from parcel_mod_contacts.models import Contact
from parcel_mod_contacts.reports.directory import (
    ContactsDirectoryParams,
    directory_data,
)
from parcel_sdk import ReportContext

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def seeded_contacts(db_session):
    """Seed three contacts spread across two days and two companies."""
    now = datetime.now(timezone.utc)
    rows = [
        Contact(id=uuid4(), name="Alice", company="Acme", created_at=now - timedelta(days=2)),
        Contact(id=uuid4(), name="Bob", company="Acme", created_at=now - timedelta(days=1)),
        Contact(id=uuid4(), name="Carol", company="Globex", created_at=now),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()
    return rows


async def test_directory_no_filters_returns_all(db_session, seeded_contacts) -> None:
    ctx = ReportContext(
        session=db_session, user_id=uuid4(), params=ContactsDirectoryParams()
    )
    out = await directory_data(ctx)
    assert out["total"] == 3
    # Latest first.
    assert [c.name for c in out["contacts"]] == ["Carol", "Bob", "Alice"]
    assert "all contacts" in out["param_summary"]


async def test_directory_company_filter_case_insensitive(db_session, seeded_contacts) -> None:
    ctx = ReportContext(
        session=db_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="acme"),
    )
    out = await directory_data(ctx)
    assert {c.name for c in out["contacts"]} == {"Alice", "Bob"}
    assert "company" in out["param_summary"]


async def test_directory_created_after_inclusive(db_session, seeded_contacts) -> None:
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    ctx = ReportContext(
        session=db_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(created_after=yesterday),
    )
    out = await directory_data(ctx)
    # Today + yesterday remain; two-days-ago drops.
    assert {c.name for c in out["contacts"]} == {"Bob", "Carol"}


async def test_directory_created_before_exclusive(db_session, seeded_contacts) -> None:
    today = date.today()
    ctx = ReportContext(
        session=db_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(created_before=today),
    )
    out = await directory_data(ctx)
    # Anything created strictly before midnight today.
    assert {c.name for c in out["contacts"]} == {"Alice", "Bob"}


async def test_directory_combined_filters_and(db_session, seeded_contacts) -> None:
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    ctx = ReportContext(
        session=db_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="Acme", created_after=yesterday),
    )
    out = await directory_data(ctx)
    assert [c.name for c in out["contacts"]] == ["Bob"]


async def test_directory_empty_result(db_session) -> None:
    ctx = ReportContext(
        session=db_session,
        user_id=uuid4(),
        params=ContactsDirectoryParams(company="DoesNotExist"),
    )
    out = await directory_data(ctx)
    assert out["total"] == 0
    assert out["contacts"] == []
```

(Reuse the existing `db_session` fixture used by the contacts test suite — see `modules/contacts/tests/conftest.py`. If the fixture is named differently, adjust.)

- [ ] **Step 3: Run and verify failure**

```bash
uv run pytest modules/contacts/tests/test_contacts_report_directory.py -v
```

Expected: ImportError on `parcel_mod_contacts.reports.directory`.

- [ ] **Step 4: Implement the data fn**

`modules/contacts/src/parcel_mod_contacts/reports/__init__.py`:

```python
from parcel_mod_contacts.reports.directory import directory_report

__all__ = ["directory_report"]
```

`modules/contacts/src/parcel_mod_contacts/reports/directory.py`:

```python
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from parcel_mod_contacts.models import Contact
from parcel_sdk import Report, ReportContext


class ContactsDirectoryParams(BaseModel):
    company: str | None = None
    created_after: date | None = None
    created_before: date | None = None


def _to_dt(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


async def directory_data(ctx: ReportContext) -> dict[str, Any]:
    p: ContactsDirectoryParams = ctx.params  # type: ignore[assignment]
    stmt = select(Contact).order_by(Contact.created_at.desc())
    if p.company:
        stmt = stmt.where(Contact.company.ilike(f"%{p.company}%"))
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
```

- [ ] **Step 5: Run the data-fn tests**

```bash
uv run pytest modules/contacts/tests/test_contacts_report_directory.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/reports/ \
        modules/contacts/tests/test_contacts_report_directory.py
git commit -m "feat(contacts): add directory report data function"
```

---

## Task 13: Contacts — directory template + manifest wire-up

**Files:**
- Create: `modules/contacts/src/parcel_mod_contacts/templates/reports/directory.html`
- Modify: `modules/contacts/src/parcel_mod_contacts/__init__.py`
- Modify: `modules/contacts/pyproject.toml`

- [ ] **Step 1: Write the directory template**

`modules/contacts/src/parcel_mod_contacts/templates/reports/directory.html`:

```html
{% extends "reports/_report_base.html" %}
{% block content %}
  <p>Total: <strong>{{ total }}</strong> contact{{ "" if total == 1 else "s" }}</p>
  {% if contacts %}
    <table>
      <thead>
        <tr><th>Name</th><th>Email</th><th>Phone</th><th>Company</th><th>Created</th></tr>
      </thead>
      <tbody>
        {% for c in contacts %}
          <tr>
            <td>{{ c.name }}</td>
            <td>{{ c.email or "—" }}</td>
            <td>{{ c.phone or "—" }}</td>
            <td>{{ c.company or "—" }}</td>
            <td>{{ c.created_at.strftime("%Y-%m-%d") }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p>No contacts match the selected filters.</p>
  {% endif %}
{% endblock %}
```

- [ ] **Step 2: Wire the report into the manifest and bump version**

Edit `modules/contacts/src/parcel_mod_contacts/__init__.py`:

```python
from __future__ import annotations

from pathlib import Path

from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_mod_contacts.models import metadata
from parcel_mod_contacts.reports import directory_report
from parcel_mod_contacts.router import router
from parcel_mod_contacts.sidebar import SIDEBAR_ITEMS
from parcel_sdk import Module, Permission

module = Module(
    name="contacts",
    version="0.3.0",
    permissions=(
        Permission("contacts.read", "View contacts and companies"),
        Permission("contacts.write", "Create, update, and delete contacts and companies"),
    ),
    capabilities=(),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=SIDEBAR_ITEMS,
    dashboards=(overview_dashboard,),
    reports=(directory_report,),
)

__all__ = ["module"]
```

Edit `modules/contacts/pyproject.toml`. Find the `version = "0.1.0"` line under `[project]` and change it to `version = "0.3.0"`.

- [ ] **Step 3: End-to-end test the report through the live app**

Add a small integration test that spins up the app and hits the contacts directory endpoints. Append to `modules/contacts/tests/test_contacts_report_directory.py`:

```python
async def test_directory_endpoints_via_app(authed_client, seeded_contacts) -> None:
    # Form
    r = await authed_client.get("/reports/contacts/directory")
    assert r.status_code == 200
    assert "Contacts directory" in r.text

    # HTML render
    r = await authed_client.get("/reports/contacts/directory/render")
    assert r.status_code == 200
    assert "Carol" in r.text

    # PDF
    r = await authed_client.get("/reports/contacts/directory/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
```

(`authed_client` and `seeded_contacts` come from existing contacts test fixtures; `seeded_contacts` was added in Task 12.)

- [ ] **Step 4: Run all contacts tests**

```bash
uv run pytest modules/contacts/tests/ -v
```

Expected: all green, including the new endpoint test.

- [ ] **Step 5: Commit**

```bash
git add modules/contacts/src/parcel_mod_contacts/__init__.py \
        modules/contacts/src/parcel_mod_contacts/templates/reports/ \
        modules/contacts/pyproject.toml \
        modules/contacts/tests/test_contacts_report_directory.py
git commit -m "feat(contacts): ship directory report + bump to 0.3.0"
```

---

## Task 14: Documentation

**Files:**
- Modify: `docs/module-authoring.md`
- Create: `docs/reports-authoring.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a "Reports" section to `module-authoring.md`**

Read the current file to find the natural insertion point (after the "Dashboards" section). Append a new section titled `## Reports` covering:

- Declaring a `Report` on `Module.reports`.
- Writing the template (extends `reports/_report_base.html`, override `{% block page_css %}` and `{% block content %}`).
- Parameter forms — Pydantic auto-render, supported types (str, int, float, bool, date, datetime, Literal, Enum), escape hatches (`json_schema_extra={"widget": "textarea"}`, `Field(description=...)`, `Report.form_template`).
- Permission model — point at one of the module's own permissions; no shell-level `reports.*` permission.
- The three URLs the shell mounts per report.
- A worked example (the Contacts directory report — same code as Task 12).

Keep the section under 200 lines. Cross-reference `docs/reports-authoring.md` for a longer walk-through.

- [ ] **Step 2: Write `docs/reports-authoring.md`**

A standalone end-to-end walk-through: starting from `parcel new-module sales`, scaffolding a "Sales pipeline" report with a Pydantic param model, writing the data fn, the template, and exercising it through the form / preview / PDF URLs. Include the directory-listing screenshots-equivalent (in text: what the user sees on each URL).

- [ ] **Step 3: Update `CLAUDE.md`**

Edit `CLAUDE.md`:

1. **Phased roadmap table** — flip Phase 9 from `⏭ next` to `✅ done` and Phase 10 from blank to `⏭ next`.
2. **Current phase** paragraph — replace the Phase 8 description with a Phase 9 description: modules declare `Report(...)` tuples on their manifest; shell auto-mounts `/reports/<module>/<slug>` (form), `.../render` (HTML preview in chrome), `.../pdf` (downloadable PDF); five field types supported by the auto-renderer plus textarea escape; per-report permission gating; no new shell migrations or shell permissions; SDK bumped to `0.5.0`; Contacts ships a `contacts.directory` reference report and bumps to `0.3.0`. Note WeasyPrint 62.x as the PDF engine (pure Python, CSS print model). Tests count goes from 296 → roughly 336.
3. **Locked-in decisions** — add a Phase-9 block summarising the eight key decisions verbatim from the spec's "Locked decisions" table.
4. **Next** pointer — Phase 10 (Workflows). Prompt unchanged: "Begin Phase 10 per `CLAUDE.md` roadmap."
5. **Phase 9 scope section** — replace `⏭ next` with `✅ shipped`, mirroring how Phase 8's scope section was updated.

- [ ] **Step 4: Run `pyright` and the full suite once before final commit**

```bash
uv run pyright
uv run ruff check
uv run ruff format --check
uv run pytest -q
```

Expected: green. Test count ~336 (296 before + ~40 new).

- [ ] **Step 5: Commit**

```bash
git add docs/module-authoring.md docs/reports-authoring.md CLAUDE.md
git commit -m "docs: phase 9 reports authoring guide + CLAUDE.md update"
```

---

## Task 15: Final verification

- [ ] **Step 1: Boot the dev server and click through manually**

```bash
docker compose up -d
uv run parcel migrate
uv run parcel install ./modules/contacts  # if needed; otherwise it's already installed
uv run parcel dev
```

In a browser:

1. Log in as the seeded admin.
2. Confirm the sidebar shows a "Reports" section with `Contacts: Contacts directory`.
3. Click it — the form renders with three optional inputs.
4. Run with no filters — see all seeded contacts.
5. Filter by company — narrows the list.
6. Click "Download PDF" — receive a PDF with the page header / footer / counter.
7. Trigger a validation error (e.g., invalid date) — form re-renders with an inline error, no 500.

If the manual click-through reveals a UI rough edge (label wording, spacing), patch it inline.

- [ ] **Step 2: Stop the dev server**

```bash
docker compose down
```

- [ ] **Step 3: Run the full test suite one more time**

```bash
uv run pytest -q
```

Expected: ~336 passed.

- [ ] **Step 4: If manual fixes were made, commit them**

```bash
git status
# If any changes:
git add -A
git commit -m "fix(reports): UI polish from manual smoke test"
```

- [ ] **Step 5: Done**

The branch is now ready for PR. The spec's "Tests" target (~40 new, ~336 total) should be met. CLAUDE.md reflects Phase 9 ✅. Phase 10 is the next session's prompt.

---

## Self-review checklist (run before handoff)

- [x] **Spec coverage:** every locked decision has a task — PDF engine (Task 3-4), declaration shape (Tasks 1-2), param model + auto-rendered form (Tasks 5-6), URL surface (Task 9), permission model (Tasks 9-10), auth-failure 404 (Task 9), sidebar (Task 10), base template (Task 7), reference report (Tasks 12-13), SDK 0.5.0 (Task 1), Contacts 0.3.0 (Task 13), boot validation warning (Task 11), docs (Task 14).
- [x] **Placeholder scan:** no "TBD", "implement later", or "similar to Task N" — every code step shows actual code.
- [x] **Type consistency:** `ReportContext(session, user_id, params)` used uniformly in tests and route code; `Report(slug, title, permission, template, data, params, form_template)` matches in SDK and consumers.
- [x] **Spec deviations:** flagged at the top of the doc (User → user_id, module title fallback, Contacts version starting point, base_url for WeasyPrint).

---

**Plan complete. Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.
