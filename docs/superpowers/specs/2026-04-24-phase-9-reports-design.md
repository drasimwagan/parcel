# Phase 9 — Reports + PDF generation

**Status:** approved
**Date:** 2026-04-24
**Builds on:** Phase 8 (Dashboards) — mirrors its registry, mounting, sidebar, and per-module-permission patterns.
**Next:** Phase 10 (Workflows) will reuse this surface for "generate report" actions.

## Goal

Modules declare `Report` objects on their manifest. The shell auto-mounts three URLs per report: a parameter form, an HTML preview, and a PDF export. Users fill out the form, preview the result in admin chrome, and download a printable PDF. Contacts ships a reference `contacts.directory` report.

## Non-goals (Phase 9)

- Charts / visuals inside reports — text + tables only this phase.
- CSV / XLSX export — deferred to Phase 10 (workflow actions can attach exports).
- Scheduled or emailed reports — deferred to Phase 10 (workflow trigger + `generate_report` action).
- Async / queued PDF generation, caching — deferred until Phase 10/11 introduce ARQ.
- AI-generated reports' static-analysis rules — tracked alongside the existing dashboards SQL-string-literal follow-up; lands when Phase 11 wires AI generation through dashboards/reports.

## Locked decisions

| Area | Decision |
|---|---|
| PDF engine | **WeasyPrint** (latest 62.x). Pure Python, CSS print model, no JS, no browser subprocess. Added to `parcel-shell` runtime deps. Modules and SDK do not import it. |
| Declaration shape | `Module.reports: tuple[Report, ...] = ()`. `Report` is a frozen `kw_only=True` dataclass on the SDK, mirroring `Dashboard`. |
| Param model | Optional Pydantic `BaseModel` subclass on `Report.params`. `None` means the report takes no parameters. |
| Form rendering | Auto-rendered from the Pydantic model by default. `Report.form_template` is an optional Jinja path override. |
| URL surface | Three URLs per report: `/reports/<module>/<slug>` (form), `/reports/<module>/<slug>/render?<params>` (HTML preview in chrome), `/reports/<module>/<slug>/pdf?<params>` (downloadable PDF). |
| Permission model | Per-report only. `Report.permission` references a permission the module already owns. No new shell-level `reports.*` permissions, no new shell migrations. |
| Auth failures | Logged-out → 303 to `/login`. Missing permission or unknown report → 404 (consistent with dashboards / AI chat). |
| Sidebar | Auto-injected per-report links (matching Phase 8 dashboards exactly), one entry per visible report. No "Reports" section header rendered when the user has zero visible reports. |
| Base template | Single opinionated `_report_base.html`: A4 portrait, 20mm margins, page-counter footer, title + generated-at + parameter-summary header. Override via `{% block page_css %}` for landscape/Letter/custom margins. |
| Charts | Out of scope. Text + tables only. Charts may land later as SDK SVG helpers (`line_svg`, `bar_svg`) once we have multiple real reports to inform the API. |
| Reference report | `contacts.directory`, params `company` / `created_after` / `created_before`, paginated table output. Permission: `contacts.read`. |
| SDK version | Bumped to **0.5.0** (added `Report`, `ReportContext`). |
| Contacts version | Bumped to **0.3.0** (manifest gains `reports=(...)`, runtime adds template + data fn). |

## Architecture

```
parcel_shell/
  reports/
    __init__.py              # mounting helpers (mirrors dashboards/)
    routes.py                # mount_reports(app, manifest) — adds the 3 routes per report
    forms.py                 # render_form(model, values, errors) -> str
    pdf.py                   # html_to_pdf(html: str, *, base_url: str) -> bytes
    templates/
      reports/
        _form.html           # admin-chrome wrapper around the parameter form
        _html_chrome.html    # admin-chrome wrapper around the rendered report (HTML preview)
        _report_base.html    # base template module reports extend (page CSS + header/footer)
        _error.html          # generic error page (validation/render/pdf failures)
  ui/
    sidebar.py               # gains _reports_section(user, manifest)
```

```
parcel_sdk/
  __init__.py                # exports Report, ReportContext (already exports Module, Dashboard, etc.)
  reports.py                 # Report and ReportContext dataclasses
```

```
modules/contacts/src/parcel_mod_contacts/
  __init__.py                # manifest gains reports=(directory_report,)
  reports/
    __init__.py
    directory.py             # ContactsDirectoryParams + directory_data + directory_report
  templates/
    reports/
      directory.html         # extends _report_base.html
```

`mount_reports(app, manifest)` is called from `create_app()` immediately after `mount_dashboards(...)`. It iterates `manifest.modules` and registers the three FastAPI routes per declared report. Like dashboards, mounting reads from `app.state.active_modules_manifest` so the loader's existing module-activation flow Just Works at boot and on install.

## SDK surface

```python
# parcel_sdk/reports.py

from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk.users import User  # existing


@dataclass(frozen=True)
class ReportContext:
    session: AsyncSession
    user: User
    params: BaseModel | None        # validated instance of Report.params, or None when params is None


@dataclass(frozen=True, kw_only=True)
class Report:
    slug: str                       # url-safe; unique per module; matches r"^[a-z0-9_-]+$"
    title: str
    permission: str                 # must be one of the module's declared permissions
    template: str                   # Jinja path inside module's templates_dir, e.g. "reports/directory.html"
    data: Callable[[ReportContext], Awaitable[dict[str, Any]]]
    params: type[BaseModel] | None = None
    form_template: str | None = None  # override Jinja partial for the parameter form
```

`Module.reports: tuple[Report, ...] = ()` is added to the existing `Module` dataclass in `parcel_sdk/__init__.py`. Backward compatible — modules that don't declare reports get the empty default.

A boot-time validation pass (in `parcel_shell.modules.service.sync_active_modules`) warns via `structlog` if any `Report.permission` is not in the module's declared permission list. Mirrors the dashboards follow-up planned in CLAUDE.md.

## URL surface

All three routes are mounted under `/reports/<module>/<slug>` and require an authenticated user with `Report.permission`. Path params: `module` (the module's `name`), `slug` (the report's `slug`). All three return 404 if the report is not found, the user lacks permission, or the module is inactive — never 403, to avoid leaking the existence of reports.

| Method | Path | Behavior |
|---|---|---|
| GET | `/reports/<module>/<slug>` | Renders the parameter form (auto-rendered or `form_template`) wrapped in admin chrome. If `report.params is None`, immediately 303s to `/render`. |
| GET | `/reports/<module>/<slug>/render` | Validates querystring against `report.params`. On `ValidationError`, re-renders the form with errors and HTTP 200 (HTMX-friendly). On success, calls `report.data(ctx)`, renders `report.template` extending `_report_base.html`, wraps in `_html_chrome.html`, returns HTML. |
| GET | `/reports/<module>/<slug>/pdf` | Same validation. On success, renders `report.template` extending `_report_base.html` standalone (no admin chrome) and pipes through WeasyPrint. Returns `application/pdf` with `Content-Disposition: attachment; filename="<module>-<slug>-<YYYYMMDD-HHMM>.pdf"`. |

Param encoding: standard URL-encoded querystring. Pydantic parses via `model.model_validate(dict(request.query_params))` with empty strings coerced to `None` for optional fields.

## Form auto-render

`parcel_shell.reports.forms.render_form(model: type[BaseModel], values: dict[str, Any], errors: dict[str, list[str]]) -> str` walks `model.model_fields` and emits a Tailwind-styled `<form>` wired for HTMX (`hx-get` to `/render`, `hx-target=#report-content`, `hx-push-url=true`).

| Pydantic field type | HTML control |
|---|---|
| `str` | `<input type="text">` |
| `int`, `float` | `<input type="number">` |
| `bool` | `<input type="checkbox">` |
| `date` | `<input type="date">` |
| `datetime` | `<input type="datetime-local">` |
| `Literal[...]`, `Enum` subclass | `<select>` with one `<option>` per literal/enum value |
| `Optional[T]` | render as `T`, `required` flag dropped |

Documented escape hatches:

- `Field(json_schema_extra={"widget": "textarea"})` → `<textarea>` instead of text input.
- `Field(description="…")` → rendered as the field's helper text under the input.
- Anything more exotic → set `Report.form_template` and write a custom Jinja partial. The shell passes `{values, errors, model}` to the override template.

Validation errors come from Pydantic's `ValidationError.errors()` and are grouped by field; rendering shows them inline below the relevant input in red.

## Templates

### `_report_base.html` (module reports extend this)

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
    th, td { text-align: left; padding: 4pt 6pt; border-bottom: 1px solid #ddd; }
    th { background: #f5f5f5; font-weight: 600; }
    {% block page_css %}{% endblock %}
  </style>
</head>
<body>
  <header>
    <h1>{{ report.title }}</h1>
    <div class="meta">
      Generated {{ generated_at.strftime("%Y-%m-%d %H:%M") }}
      {% if param_summary %}· {{ param_summary }}{% endif %}
    </div>
  </header>
  {% block content %}{% endblock %}
</body>
</html>
```

### `_html_chrome.html`

Extends `parcel_shell/templates/_base.html`. Renders the report's `<body>` content inside `<div id="report-content">` plus a sticky toolbar with "Edit filters" (back to form) and "Download PDF" (link to `/pdf?<params>`).

### `_form.html`

Extends `_base.html`. Contains the rendered form (auto or override) and a submit button. HTMX swaps the form-or-results region without a full reload.

## PDF generation

```python
# parcel_shell/reports/pdf.py

from __future__ import annotations
import weasyprint

def html_to_pdf(html: str, *, base_url: str) -> bytes:
    return weasyprint.HTML(string=html, base_url=base_url).write_pdf()
```

`base_url` is set to the shell's static root so `/static/...` references in templates resolve. The PDF route wraps the call in `try/except` mirroring dashboards' widget isolation:

```python
try:
    html = render_template(report.template, ctx)         # extends _report_base.html, no admin chrome
    pdf_bytes = html_to_pdf(html, base_url=settings.static_root)
except Exception as exc:
    logger.exception("report.pdf_failed", module=module.name, slug=report.slug, params=params.model_dump() if params else None)
    set_flash(request, "error", "Could not generate the PDF. Please try again.")
    return RedirectResponse(f"/reports/{module.name}/{report.slug}", status_code=303)
return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={...})
```

No partial PDFs ever leave the server. WeasyPrint's `URLFetchingError`, layout errors, and template render errors all funnel through the same catch.

## Sidebar

`_reports_section(user, manifest)` in `parcel_shell/ui/sidebar.py` iterates each mounted module's `reports` tuple and emits one sidebar entry per report the user has permission for. Insertion order: after `_dashboards_section`. If the user has zero visible reports across all mounted modules, the function returns `None` and the section disappears entirely.

Each entry: `{module.title}: {report.title}` linking to `/reports/<module>/<slug>`. Identical to the dashboards section.

## Reference report — `contacts.directory`

```python
# modules/contacts/src/parcel_mod_contacts/reports/directory.py

from __future__ import annotations
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from parcel_sdk import Report, ReportContext

from parcel_mod_contacts.models import Contact


class ContactsDirectoryParams(BaseModel):
    company: str | None = None
    created_after: date | None = None
    created_before: date | None = None


async def directory_data(ctx: ReportContext) -> dict[str, Any]:
    p: ContactsDirectoryParams = ctx.params  # type: ignore[assignment]
    stmt = select(Contact).order_by(Contact.created_at.desc())
    if p.company:
        stmt = stmt.where(Contact.company.ilike(f"%{p.company}%"))
    if p.created_after:
        stmt = stmt.where(Contact.created_at >= p.created_after)
    if p.created_before:
        stmt = stmt.where(Contact.created_at < p.created_before)
    contacts = (await ctx.session.scalars(stmt)).all()
    summary_bits: list[str] = []
    if p.company:
        summary_bits.append(f"company contains '{p.company}'")
    if p.created_after:
        summary_bits.append(f"after {p.created_after.isoformat()}")
    if p.created_before:
        summary_bits.append(f"before {p.created_before.isoformat()}")
    return {
        "contacts": contacts,
        "total": len(contacts),
        "param_summary": "; ".join(summary_bits) if summary_bits else "all contacts",
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

```html
{# modules/contacts/src/parcel_mod_contacts/templates/reports/directory.html #}
{% extends "reports/_report_base.html" %}
{% block content %}
  <p>Total: <strong>{{ total }}</strong> contacts</p>
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

`parcel_mod_contacts/__init__.py` adds `reports=(directory_report,)` to its `Module(...)` constructor and bumps `version="0.3.0"`.

## Tests

Target: ~40 new tests, ~336 total. Coverage:

**SDK** (`tests/test_sdk_reports.py`)
- `Report` is frozen, `kw_only=True`, requires the right fields.
- `ReportContext` is frozen.
- `Module.reports` defaults to `()`.

**Form auto-render** (`tests/test_reports_forms.py`)
- One test per supported field type (str, int, float, bool, date, datetime, Literal, Enum).
- Optional fields drop `required`.
- `description` renders as helper text.
- Pydantic `ValidationError` surfaces field-grouped error messages.
- `widget=textarea` escape hatch.
- `form_template` override is rendered with `{values, errors, model}`.

**Routing** (`tests/test_reports_routes.py`)
- For each of the 3 endpoints: logged-out → 303 to `/login`; missing permission → 404; unknown module/slug → 404.
- Form GET renders for a report with `params=None` → 303 to `/render`.
- `/render` validation error → 200 with errors visible, no DB hit on `report.data`.
- `/render` success returns HTML containing report content inside admin chrome.
- `/pdf` returns `application/pdf` with non-empty body and the right `Content-Disposition`.
- `/pdf` failure path (forced by patching `html_to_pdf` to raise) → 303 to form with flash error and structured log.

**Sidebar** (`tests/test_sidebar_reports.py`)
- Entry appears for users with permission.
- Entry suppressed for users without permission.
- Section disappears when zero reports are visible.

**Contacts directory** (`tests/test_contacts_report_directory.py`)
- No params → all contacts, latest first.
- `company` filter is case-insensitive contains.
- `created_after` / `created_before` filter correctly (boundary inclusive on `after`, exclusive on `before`).
- Combined filters AND together.
- Empty result renders the empty-state message.

**Boot validation** (`tests/test_modules_service.py` extension)
- A report whose `permission` isn't in the module's permission list emits a `structlog.warning`. Mirror of the planned dashboard follow-up.

## Documentation

- `docs/module-authoring.md` gains a "Reports" section: declaring a `Report`, writing the template, page-CSS conventions, parameter forms (auto-render + override), permission model, sample fixture.
- `CLAUDE.md` "Phased roadmap" row 9 → ✅; "Locked-in decisions" gains a Phase-9 block summarising the table above; "Current phase" paragraph rewritten to describe Phase 9; "Next" pointer updated to Phase 10 (Workflows).
- New file `docs/reports-authoring.md` with a worked example (the Contacts directory report end-to-end). Optional this phase if `module-authoring.md` is enough.

## Migration / compatibility

- No new shell migrations. No new shell permissions.
- SDK 0.5.0 is additive — existing `Module(...)` calls still type-check (new field has a default).
- Contacts 0.3.0 adds the report; no contacts schema change, no contacts migration.
- WeasyPrint requires native libs (cairo, pango, gdk-pixbuf, libffi) on the shell image. Dockerfile gets one apt-get line; documented in `docker/Dockerfile`.

## Risks and follow-ups

- **WeasyPrint native-deps in Docker.** Adds a few hundred MB of system libs. Acceptable; documented.
- **Param-summary on header.** Trivial today, but as parameter models grow more complex (nested models, enums) the auto-summary may get unwieldy. Punt: modules can override the header by overriding `_report_base.html` blocks if it ever becomes painful.
- **Auto-rendered form covers ~90%.** Anything outside the supported type set requires `form_template`. Document this clearly.
- **No async PDF generation.** PDFs render synchronously on the request. Acceptable while WeasyPrint stays fast on the kinds of reports we ship; if a report grows beyond a few seconds, Phase 10's ARQ infra absorbs it.
- **AI-generator awareness.** When Phase 11 wires AI generation through reports, the static-analysis gate needs to (a) ensure `Report.template` resolves to a file the module ships, (b) extend the existing dashboards "first-arg-string-literal" rule to any new SDK helpers we add. Tracked alongside the existing dashboards follow-up; not blocked by Phase 9.

## Open during implementation

None. All eight key questions are locked. Implementation can proceed straight to plan-writing.
