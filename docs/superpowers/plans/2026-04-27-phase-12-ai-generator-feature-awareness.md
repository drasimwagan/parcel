# Phase 12 — AI Generator Feature Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` so the Claude generator produces modules that use dashboards (Phase 8), reports (Phase 9), workflows (Phase 10), and seed.py (Phase 11), pinned to a network-only capability rule.

**Architecture:** Single-file prompt rewrite. No SDK / shell / provider / migration changes. Three new tests under `packages/parcel-shell/tests/`. The new prompt embeds a complete `support_tickets` worked reference module that demonstrates every feature the model is allowed to emit; the model pattern-matches against it for structure. Discipline rules ("Feature menu") tell the model when to add each feature and the capability rule pins AI generation to `network`-only.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, parcel-sdk 0.10.0, parcel-gate (existing), pytest. No new deps.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` | Modify | Rewritten system prompt — current ~350 lines → new ~750 lines. |
| `packages/parcel-shell/tests/test_ai_prompt_shape.py` | Create | Static assertions: prompt loads, contains feature markers, capability rule pinned. |
| `packages/parcel-shell/tests/test_ai_prompt_reference_module.py` | Create | Extracts the embedded `support_tickets` reference and runs it through the Phase-7a static-analysis gate. |
| `packages/parcel-shell/tests/test_ai_prompt_live_generation.py` | Create | Skipped-by-default integration test that hits the live Anthropic API. |
| `CLAUDE.md` | Modify | Three new locked-in-decision rows + roadmap flip + Phase 12 shipped section + current-phase prose. |
| `docs/index.html` | Modify | Roadmap grid: add Phase 12 done; update stat-line. |

---

## Task 1: Failing static prompt-shape test

**Files:**
- Create: `packages/parcel-shell/tests/test_ai_prompt_shape.py`

- [ ] **Step 1: Write the test file**

Create `packages/parcel-shell/tests/test_ai_prompt_shape.py`:

```python
"""Static assertions on the AI generator's system prompt.

These are cheap regression guards. They do not exercise the live model;
they exercise the file the live model loads. If a future edit drops a
feature section by accident, these tests catch it.

The prompt is loaded the same way the live provider loads it
(``importlib.resources``) so any drift between the file on disk and
what the provider sees is caught here too.
"""

from __future__ import annotations

import importlib.resources

import pytest


def _prompt_text() -> str:
    return (
        importlib.resources.files("parcel_shell.ai.prompts")
        .joinpath("generate_module.md")
        .read_text(encoding="utf-8")
    )


def test_prompt_loads_and_is_substantial() -> None:
    """Lower bound only — Phase 12 grew the prompt to ~750 lines (~30 KiB)."""
    text = _prompt_text()
    assert len(text) > 5000


@pytest.mark.parametrize(
    "marker",
    [
        # Feature surfaces the model must know about.
        "Module.dashboards",
        "Module.workflows",
        "Module.reports",
        "Module.workflow_functions",
        "seed.py",
        "shell_api.emit",
        # Worked-reference markers.
        "support_tickets",
        "KpiWidget",
        "BarWidget",
        "OnCreate",
        "SendEmail",
        # Discipline-section markers.
        "ALWAYS include",
        "INCLUDE BY DEFAULT",
        "ONLY IF THE USER ASKS",
    ],
)
def test_prompt_documents_each_feature(marker: str) -> None:
    assert marker in _prompt_text(), f"prompt missing required marker: {marker!r}"


def test_capability_rule_is_network_only() -> None:
    """The AI generator must be told it can add network but never the others."""
    text = _prompt_text()
    # Phrasing is fixed so a permissive rewrite is a noisy regression.
    assert "network: REQUIRED if" in text
    assert "filesystem / process / raw_sql: NEVER add" in text


def test_prompt_keeps_existing_hard_rules() -> None:
    """Hard rules from Phase 7b carry forward unchanged. Failure here means a
    rewrite accidentally dropped a security-critical clause."""
    text = _prompt_text()
    for clause in [
        "Imports `sys` or `importlib`",
        "Imports anything from `parcel_shell.*`",
        "Calls `eval`, `exec`, `compile`, or `__import__`",
        "__class__",
        "__subclasses__",
    ]:
        assert clause in text, f"hard-rule clause missing: {clause!r}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest packages/parcel-shell/tests/test_ai_prompt_shape.py -v`
Expected: most parametrize variants FAIL because the current Phase-7c prompt does not contain the new feature markers (`Module.dashboards`, `Module.workflows`, `Module.reports`, `seed.py`, `support_tickets`, `KpiWidget`, etc.). `test_prompt_loads_and_is_substantial` and `test_prompt_keeps_existing_hard_rules` should PASS — they describe behaviour that's already true today.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/test_ai_prompt_shape.py
git commit -m "test(ai): static shape assertions for generate_module.md"
```

---

## Task 2: Rewrite the system prompt

**Files:**
- Modify: `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` (full overwrite)

This task is one mechanical action: replace the file contents with the full new prompt below. The embedded `support_tickets` reference module is what the model pattern-matches against; the discipline section is what tells it when to add each feature.

- [ ] **Step 1: Write the new prompt**

Overwrite `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` with **exactly** this content:

````markdown
# Parcel module generator — system prompt

You are writing a Parcel module. Your output will be run through a strict
static-analysis gate (ruff + bandit + a custom AST policy). Emit **only tool
calls** — no prose, no explanations. If you need to explain a design choice,
put it in a code comment.

## Tool contract

- `write_file(path: str, content: str)` — write one file. Call once per file.
  - `path` is relative to the module root, uses POSIX separators, never
    absolute, never contains `..`, never ends in `.sh`/`.exe`/`.so`/`.dll`.
  - `content` is the full text of the file.
- `submit_module()` — call **exactly once** when the module is complete.

## Module layout

Always emit:

```
pyproject.toml
README.md
src/parcel_mod_<name>/__init__.py
src/parcel_mod_<name>/models.py
src/parcel_mod_<name>/router.py
src/parcel_mod_<name>/seed.py
src/parcel_mod_<name>/alembic.ini
src/parcel_mod_<name>/alembic/env.py
src/parcel_mod_<name>/alembic/script.py.mako
src/parcel_mod_<name>/alembic/versions/0001_init.py
src/parcel_mod_<name>/templates/<name>/index.html
tests/test_smoke.py
```

Emit when the user prompt asks for them (see "Feature menu" below):

```
src/parcel_mod_<name>/dashboards.py
src/parcel_mod_<name>/workflows.py
src/parcel_mod_<name>/reports.py
src/parcel_mod_<name>/templates/reports/<slug>.html   # one per report
```

## Worked reference: `support_tickets`

This is a complete, working module that uses every feature you are allowed to
emit. Pattern-match against this for structure. Compose other widget types,
trigger types, and action types from the SDK exports list further down.

### `pyproject.toml`

```toml
[project]
name = "parcel-mod-support-tickets"
version = "0.1.0"
description = "Help-desk ticketing with dashboards, a monthly volume report, and email-on-create."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = ["parcel-sdk", "fastapi>=0.115"]

[project.entry-points."parcel.modules"]
support_tickets = "parcel_mod_support_tickets:module"

[tool.uv.sources]
parcel-sdk = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parcel_mod_support_tickets"]
```

### `src/parcel_mod_support_tickets/__init__.py`

This file is load-bearing — it shows how every feature tuple sits on the
single `Module(...)` call. Copy this layout exactly and fill / remove the
feature tuples per the discipline rules.

```python
from __future__ import annotations

from pathlib import Path

from parcel_mod_support_tickets.dashboards import overview_dashboard
from parcel_mod_support_tickets.models import metadata
from parcel_mod_support_tickets.reports import monthly_volume_report
from parcel_mod_support_tickets.router import router
from parcel_mod_support_tickets.workflows import notify_on_create
from parcel_sdk import Module, Permission

module = Module(
    name="support_tickets",
    version="0.1.0",
    permissions=(
        Permission("support_tickets.read", "View tickets"),
        Permission("support_tickets.write", "Create and edit tickets"),
    ),
    capabilities=("network",),  # required by SendEmail action below
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=(),
    dashboards=(overview_dashboard,),
    reports=(monthly_volume_report,),
    workflows=(notify_on_create,),
    workflow_functions={},
)

__all__ = ["module"]
```

### `src/parcel_mod_support_tickets/models.py`

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, MetaData, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

metadata = MetaData(schema="mod_support_tickets")


class TicketBase(DeclarativeBase):
    metadata = metadata  # type: ignore[assignment]


class Ticket(TicketBase):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    comments: Mapped[list["Comment"]] = relationship(back_populates="ticket")


class Comment(TicketBase):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    ticket: Mapped[Ticket] = relationship(back_populates="comments")
```

### `src/parcel_mod_support_tickets/router.py`

The `shell_api.emit(...)` call is what makes workflows fire. Without this
line, an `OnCreate` workflow declared on the same module never runs.

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_mod_support_tickets.models import Ticket
from parcel_sdk import shell_api

router = APIRouter(tags=["mod-support_tickets"])


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Any = Depends(shell_api.require_permission("support_tickets.read")),
    db: AsyncSession = Depends(shell_api.get_session()),
) -> Response:
    perms = await shell_api.effective_permissions(request, user)
    tickets = list((await db.scalars(select(Ticket).order_by(Ticket.created_at.desc()))).all())
    tpl = shell_api.get_templates()
    return tpl.TemplateResponse(
        request,
        "support_tickets/index.html",
        {
            "user": user,
            "sidebar": shell_api.sidebar_for(request, perms),
            "active_path": "/mod/support_tickets",
            "settings": request.app.state.settings,
            "tickets": tickets,
        },
    )


@router.post("/create")
async def create(
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    priority: str = Form("normal"),
    user: Any = Depends(shell_api.require_permission("support_tickets.write")),
    db: AsyncSession = Depends(shell_api.get_session()),
) -> Response:
    ticket = Ticket(title=title, body=body, priority=priority)
    db.add(ticket)
    await db.flush()
    # Fire the workflow event AFTER the row is in the session, BEFORE we redirect.
    # The shell's after_commit listener picks events up post-commit and dispatches
    # any matching workflows (e.g. notify_on_create below).
    await shell_api.emit(db, "support_tickets.ticket.created", ticket)
    return RedirectResponse("/mod/support_tickets/", status_code=303)
```

### `src/parcel_mod_support_tickets/seed.py`

This file is required for every module. The Phase-11 sandbox preview
renderer calls `seed(session)` after the schema is created and before
screenshots are taken. An empty schema produces empty preview screenshots,
which defeats the approval-gate UX. Aim for 5–10 representative records.

```python
"""Sample data for the sandbox preview renderer.

Imported by parcel_shell.sandbox.previews.seed_runner. By the time this runs,
module.metadata.schema has been patched to "mod_sandbox_<uuid>", so every
INSERT goes to the sandbox schema, not production.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_support_tickets.models import Comment, Ticket


async def seed(session: AsyncSession) -> None:
    tickets = [
        Ticket(title="Login button does nothing on Safari",
               body="Reproducible on Safari 17.", status="open", priority="high"),
        Ticket(title="Export to CSV is missing the Notes column",
               body="Excel users miss the Notes column.", status="open", priority="normal"),
        Ticket(title="Add dark mode to dashboard",
               body="Several customers asked.", status="open", priority="low"),
        Ticket(title="API rate limit too aggressive for Zapier",
               body="Zapier hits 429 within minutes.", status="in_progress", priority="high"),
        Ticket(title="Typo on pricing page",
               body="‘Profesional’ should be ‘Professional’.", status="closed", priority="low"),
        Ticket(title="Two-factor auth fails when phone has no SMS",
               body="Need TOTP fallback.", status="open", priority="high"),
        Ticket(title="Webhook timeouts on bulk imports",
               body="Imports >5k rows time out.", status="in_progress", priority="normal"),
        Ticket(title="Beta program survey results",
               body="Posted to internal slack.", status="closed", priority="low"),
    ]
    session.add_all(tickets)
    await session.flush()

    session.add_all([
        Comment(ticket_id=tickets[0].id, body="Confirmed on Safari 17.4 too."),
        Comment(ticket_id=tickets[3].id, body="Investigating with Zapier support."),
        Comment(ticket_id=tickets[3].id, body="Patch landing in 2.4.1."),
    ])
    await session.flush()
```

### `src/parcel_mod_support_tickets/dashboards.py`

```python
from __future__ import annotations

from parcel_sdk import (
    BarWidget,
    Ctx,
    Dashboard,
    Kpi,
    KpiWidget,
    scalar_query,
    series_query,
)


async def _open_count(ctx: Ctx) -> Kpi:
    n = await scalar_query(
        ctx.session,
        "SELECT COUNT(*) FROM mod_support_tickets.tickets WHERE status <> 'closed'",
    )
    return Kpi(value=int(n or 0))


async def _by_priority(ctx: Ctx):
    return await series_query(
        ctx.session,
        """
        SELECT priority AS p, COUNT(*) AS n
        FROM mod_support_tickets.tickets
        WHERE status <> 'closed'
        GROUP BY priority
        ORDER BY CASE priority
            WHEN 'high' THEN 0
            WHEN 'normal' THEN 1
            WHEN 'low' THEN 2
            ELSE 3
        END
        """,
        label_col="p",
        value_col="n",
    )


overview_dashboard = Dashboard(
    name="support_tickets.overview",
    slug="overview",
    title="Support tickets overview",
    permission="support_tickets.read",
    description="Open ticket count and priority breakdown.",
    widgets=(
        KpiWidget(id="open", title="Open tickets", data=_open_count, col_span=2),
        BarWidget(id="by_priority", title="Open by priority", data=_by_priority, col_span=4),
    ),
)
```

### `src/parcel_mod_support_tickets/reports.py`

```python
from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from parcel_mod_support_tickets.models import Ticket
from parcel_sdk import Report, ReportContext


class MonthlyVolumeParams(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="Calendar year")
    month: int = Field(..., ge=1, le=12, description="Calendar month (1=Jan)")


def _month_window(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


async def monthly_volume_data(ctx: ReportContext) -> dict[str, Any]:
    p: MonthlyVolumeParams = ctx.params  # type: ignore[assignment]
    start, end = _month_window(p.year, p.month)
    stmt = (
        select(Ticket)
        .where(Ticket.created_at >= start)
        .where(Ticket.created_at < end)
        .order_by(Ticket.created_at.asc())
    )
    tickets = list((await ctx.session.scalars(stmt)).all())
    return {
        "tickets": tickets,
        "total": len(tickets),
        "year": p.year,
        "month": p.month,
        "param_summary": f"{p.year}-{p.month:02d}",
    }


monthly_volume_report = Report(
    slug="monthly-volume",
    title="Monthly ticket volume",
    permission="support_tickets.read",
    template="reports/monthly_volume.html",
    data=monthly_volume_data,
    params=MonthlyVolumeParams,
)
```

### `src/parcel_mod_support_tickets/workflows.py`

```python
from __future__ import annotations

from parcel_sdk import OnCreate, SendEmail, Workflow

notify_on_create = Workflow(
    slug="notify_on_create",
    title="Email triage on new ticket",
    permission="support_tickets.read",
    triggers=(OnCreate("support_tickets.ticket.created"),),
    actions=(
        SendEmail(
            to="triage@example.com",
            subject="New ticket: {{ subject.title }}",
            body="A new ticket was filed:\n\n{{ subject.body }}\n\nPriority: {{ subject.priority }}",
        ),
    ),
    description="Notifies the triage inbox when a ticket is created.",
)
```

### `src/parcel_mod_support_tickets/templates/support_tickets/index.html`

```html
{% extends "_base.html" %}
{% block content %}
<h1>Support tickets</h1>
<form method="post" action="/mod/support_tickets/create" style="margin-bottom:1.5rem">
  <input name="title" placeholder="Title" required>
  <textarea name="body" placeholder="Describe the issue"></textarea>
  <select name="priority"><option>low</option><option selected>normal</option><option>high</option></select>
  <button type="submit">Create ticket</button>
</form>
<table>
  <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Created</th></tr></thead>
  <tbody>
    {% for t in tickets %}
      <tr>
        <td>{{ t.title }}</td>
        <td>{{ t.status }}</td>
        <td>{{ t.priority }}</td>
        <td>{{ t.created_at.strftime("%Y-%m-%d %H:%M") }}</td>
      </tr>
    {% else %}
      <tr><td colspan="4">No tickets yet.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

### `src/parcel_mod_support_tickets/templates/reports/monthly_volume.html`

```html
{% extends "reports/_report_base.html" %}
{% block content %}
  <p>Total this month: <strong>{{ total }}</strong></p>
  {% if tickets %}
    <table>
      <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Created</th></tr></thead>
      <tbody>
        {% for t in tickets %}
          <tr>
            <td>{{ t.title }}</td>
            <td>{{ t.status }}</td>
            <td>{{ t.priority }}</td>
            <td>{{ t.created_at.strftime("%Y-%m-%d") }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% else %}
    <p>No tickets in this window.</p>
  {% endif %}
{% endblock %}
```

### `src/parcel_mod_support_tickets/alembic.ini`

Use the standard alembic.ini layout (omitted here for brevity) — same shape
as every other Parcel module: `script_location = %(here)s/alembic`, the four
loggers / handlers / formatters blocks, and `sqlalchemy.url` pointing at the
shell's Postgres. The shell does not read `sqlalchemy.url` at runtime
(modules use `parcel_sdk.alembic_env.run_async_migrations`), but Alembic
needs the file to be valid INI.

### `src/parcel_mod_support_tickets/alembic/env.py`

```python
from parcel_mod_support_tickets import module
from parcel_sdk.alembic_env import run_async_migrations

run_async_migrations(module)
```

### `src/parcel_mod_support_tickets/alembic/script.py.mako`

Use the standard Mako template (the same one every Parcel module uses) —
emits the `revision`, `down_revision`, `branch_labels`, `depends_on`
identifiers, plus `upgrade()` / `downgrade()` shells.

### `src/parcel_mod_support_tickets/alembic/versions/0001_init.py`

```python
"""init support_tickets

Revision ID: 0001_init
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "mod_support_tickets"')
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="mod_support_tickets",
    )
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["mod_support_tickets.tickets.id"],
            ondelete="CASCADE",
        ),
        schema="mod_support_tickets",
    )


def downgrade() -> None:
    op.execute('DROP SCHEMA IF EXISTS "mod_support_tickets" CASCADE')
```

### `tests/test_smoke.py`

```python
from __future__ import annotations

from parcel_mod_support_tickets import module


def test_module_identity() -> None:
    assert module.name == "support_tickets"
    assert module.version == "0.1.0"


def test_module_wires_features() -> None:
    assert len(module.dashboards) == 1
    assert len(module.workflows) == 1
    assert len(module.reports) == 1
    assert module.workflow_functions == {}


def test_module_capabilities_minimal() -> None:
    """SendEmail requires network. Nothing else is allowed."""
    assert module.capabilities == ("network",)
```

## Feature menu (decide per user prompt)

Use this checklist on every generation. Read the user's prompt, then walk
top-to-bottom and decide what to emit.

ALWAYS include:
- `seed.py` with 5–10 representative records, written using the module's own
  SQLAlchemy ORM via the `AsyncSession` argument. The Phase-11 sandbox
  preview renderer calls `seed(session)` after the schema is created;
  an empty schema produces empty preview screenshots and defeats the
  approval-gate UX.

INCLUDE BY DEFAULT (omit only if the data has no obvious aggregations):
- 1–2 dashboard widgets in `dashboards.py`.
  - `KpiWidget` for "how many active X".
  - `BarWidget` for "X by category".
  - `LineWidget` for "X over time".
  - `TableWidget` for "most-recent X".
  - Use `scalar_query` / `series_query` / `table_query` from `parcel_sdk` —
    pass the SQL as a literal string, never f-string or concatenate.

ONLY IF THE USER ASKS:
- Workflows in `workflows.py`. Trigger words in the user's prompt:
  "when …", "on each …", "every Monday", "email me", "post to webhook",
  "schedule", "trigger", "automate", "notify", "alert".
- Reports in `reports.py` + a Jinja template at
  `templates/reports/<slug>.html`. Trigger words: "report", "PDF",
  "export", "printable", "monthly summary", "audit document",
  "downloadable".

NEVER include unless the user explicitly specifies:
- `Module.preview_routes` — the auto-walk handles 95% of modules. Override
  only when the user describes routes that need custom path-param values
  the auto-walker cannot infer.

CAPABILITIES:
- Default: `capabilities=()`.
- `network`: REQUIRED if and only if the module uses `SendEmail` or
  `CallWebhook` actions. Add it; do not silently drop the action.
- `filesystem` / `process` / `raw_sql`: NEVER add. If the user's prompt
  seems to require them, write the module *without* that specific feature
  and leave a `# TODO` comment on the relevant line for the human reviewer.
  Do not refuse the prompt entirely.

## Facade surface (the only way to reach the shell)

Modules interact with the shell exclusively through `parcel_sdk.shell_api`:

- `shell_api.get_session()` — FastAPI dep returning an `AsyncSession`.
- `shell_api.require_permission(name)` — HTML-auth dep enforcing a permission.
- `shell_api.effective_permissions(request, user)` — user's perm set.
- `shell_api.set_flash(response, flash)` — one-shot banner.
- `shell_api.get_templates()` — shared `Jinja2Templates`.
- `shell_api.sidebar_for(request, perms)` — composed sidebar.
- `shell_api.Flash(kind, msg)` — frozen dataclass (`kind` is
  `"success" | "error" | "info"`).
- `shell_api.emit(session, event, subject, *, changed=())` — fire a workflow
  event. Call after the row mutation, before the response is returned.
  The shell's `after_commit` listener picks events up post-commit and
  dispatches matching workflows. Without an `emit` call, an `OnCreate` /
  `OnUpdate` workflow declared on the same module will never fire.

## SDK exports you can import

From `parcel_sdk`:

- Manifest: `Module`, `Permission`, `SidebarItem`, `PreviewRoute`.
- Dashboards: `Dashboard`, `Widget`, `KpiWidget`, `LineWidget`, `BarWidget`,
  `TableWidget`, `HeadlineWidget`, `Kpi`, `Series`, `Dataset`, `Table`,
  `Ctx`, `scalar_query`, `series_query`, `table_query`.
- Reports: `Report`, `ReportContext`.
- Workflows: `Workflow`, `Trigger`, `OnCreate`, `OnUpdate`, `Manual`,
  `OnSchedule`, `Action`, `UpdateField`, `EmitAudit`, `SendEmail`,
  `CallWebhook`, `RunModuleFunction`, `GenerateReport`, `WorkflowContext`.
- Plumbing: `shell_api`, `run_async_migrations`.

## Capability vocabulary

Four values, declared in `Module(capabilities=(...))`:

| Capability | Unlocks |
|---|---|
| `filesystem` | `import os`, `open(...)` |
| `process` | `import subprocess` |
| `network` | `socket`, `urllib`, `http.*`, `httpx`, `requests`, `aiohttp` |
| `raw_sql` | `sqlalchemy.text(...)` |

The "Feature menu" section above pins AI generation to `network`-only.

## Hard rules (always blocked, no capability unlocks)

The gate **will reject** any module that:

- Imports `sys` or `importlib`.
- Imports anything from `parcel_shell.*`. Use `parcel_sdk.shell_api` instead.
- Calls `eval`, `exec`, `compile`, or `__import__` (the four dynamic-code
  builtins).
- Accesses sandbox-escape dunder attributes: `__class__`, `__subclasses__`,
  `__globals__`, `__builtins__`, `__mro__`, `__code__`.

The gate **does not** scan your `tests/` directory. Keep runtime code clean;
tests can import freely.

## Allowed imports (beyond the module's own package)

Stdlib: `datetime`, `uuid`, `decimal`, `enum`, `dataclasses`, `typing`,
`typing_extensions`, `collections`, `itertools`, `functools`, `json`, `re`,
`math`, `pathlib` (path manipulation only — `open()` is still blocked),
`operator`, `contextlib`, `logging`, `warnings`, `abc`, `copy`, `hashlib`,
`base64`, `secrets`, `random`, `string`, `__future__`.

Third-party: `parcel_sdk`, `parcel_sdk.*`, `fastapi`, `starlette`,
`sqlalchemy` (except `text` without the `raw_sql` capability), `pydantic`,
`jinja2`, `alembic`.

Any import outside this allow-list produces a warning (not a failure), but
prefer sticking to the list.

## Style

- Every `.py` starts with `from __future__ import annotations`.
- Type hints on every function signature. Use `Any` when a precise type would
  require importing something outside the allow-list.
- Line length ≤ 100.
- Double quotes.
- No `# noqa` comments — write code that doesn't need them.
- No prose output — only tool calls.

## Naming

- Module name is snake_case, `[a-z][a-z0-9_]*`.
- Package name is `parcel_mod_<name>`.
- Schema name is `mod_<name>`.
- Permissions are `<name>.read` / `<name>.write`.

Now read the user's prompt and write the module. Walk the Feature menu
top-to-bottom. Call `write_file` for each file you decide to emit, then call
`submit_module` exactly once.
````

- [ ] **Step 2: Run the static-shape test to verify it now passes**

Run: `uv run pytest packages/parcel-shell/tests/test_ai_prompt_shape.py -v`
Expected: ALL PASS — every parametrised marker is now in the prompt.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md
git commit -m "feat(ai): teach generator dashboards/reports/workflows/seed.py"
```

---

## Task 3: Reference-module passes-the-gate test

**Files:**
- Create: `packages/parcel-shell/tests/test_ai_prompt_reference_module.py`

This test extracts the `support_tickets` reference module from the prompt and
runs it through the live Phase-7a static-analysis gate. As the gate evolves
this catches drift between the prompt's worked example and the gate.

- [ ] **Step 1: Write the test file**

Create `packages/parcel-shell/tests/test_ai_prompt_reference_module.py`:

```python
"""Extract the embedded support_tickets reference module from the system
prompt, materialise it on disk, and run the Phase-7a static-analysis gate
against it. Catches drift between the prompt's worked example and the gate.
"""

from __future__ import annotations

import importlib.resources
import re
import textwrap
from pathlib import Path

import pytest

from parcel_gate.runner import run_gate


def _prompt_text() -> str:
    return (
        importlib.resources.files("parcel_shell.ai.prompts")
        .joinpath("generate_module.md")
        .read_text(encoding="utf-8")
    )


# Each file in the reference is shown as:
#   ### `<path>`
#   <one or more blank lines / prose>
#   ```python (or toml/html/ini)
#   <body>
#   ```
#
# We pull (path, body) pairs out for every fence that follows a path heading.
_HEADING_RE = re.compile(r"^### `([^`]+)`\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)


def _extract_reference_files(text: str) -> dict[str, str]:
    """Return {relative_path: body} for the reference module.

    Only files under `src/parcel_mod_support_tickets/...` and
    `tests/test_smoke.py` (plus the top-level `pyproject.toml`) are materialised.
    Files documented as standard-shape (alembic.ini, script.py.mako) are
    skipped because they reference content the prompt declines to inline.
    """
    files: dict[str, str] = {}
    skip = {
        "src/parcel_mod_support_tickets/alembic.ini",
        "src/parcel_mod_support_tickets/alembic/script.py.mako",
    }
    for heading in _HEADING_RE.finditer(text):
        path = heading.group(1)
        if path in skip:
            continue
        if not (
            path.startswith("src/parcel_mod_support_tickets/")
            or path == "tests/test_smoke.py"
            or path == "pyproject.toml"
        ):
            continue
        # Find the next fence after this heading.
        rest = text[heading.end() :]
        next_heading = _HEADING_RE.search(rest)
        scope = rest[: next_heading.start()] if next_heading else rest
        fence = _FENCE_RE.search(scope)
        if fence is None:
            pytest.fail(f"reference file {path!r} has no fenced body")
        files[path] = textwrap.dedent(fence.group(1))
    return files


def test_extraction_finds_every_referenced_file() -> None:
    files = _extract_reference_files(_prompt_text())
    expected = {
        "pyproject.toml",
        "src/parcel_mod_support_tickets/__init__.py",
        "src/parcel_mod_support_tickets/models.py",
        "src/parcel_mod_support_tickets/router.py",
        "src/parcel_mod_support_tickets/seed.py",
        "src/parcel_mod_support_tickets/dashboards.py",
        "src/parcel_mod_support_tickets/reports.py",
        "src/parcel_mod_support_tickets/workflows.py",
        "src/parcel_mod_support_tickets/templates/support_tickets/index.html",
        "src/parcel_mod_support_tickets/templates/reports/monthly_volume.html",
        "src/parcel_mod_support_tickets/alembic/env.py",
        "src/parcel_mod_support_tickets/alembic/versions/0001_init.py",
        "tests/test_smoke.py",
    }
    assert expected <= files.keys(), f"missing files: {expected - files.keys()}"


def test_reference_module_passes_gate(tmp_path: Path) -> None:
    """The embedded reference must pass the same static-analysis gate that
    AI-generated modules face. Capability is `network` (the reference uses
    SendEmail). If a future gate change rejects the reference, either the
    reference or the gate is wrong — fix one of them."""
    files = _extract_reference_files(_prompt_text())
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    report = run_gate(tmp_path, declared_capabilities=frozenset({"network"}))
    errors = [f for f in report.findings if f.severity == "error"]
    assert errors == [], (
        "reference module fails the gate. errors:\n"
        + "\n".join(f"  {f.code} @ {f.path}:{f.line} — {f.message}" for f in errors)
    )
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest packages/parcel-shell/tests/test_ai_prompt_reference_module.py -v`
Expected: PASS. If it fails, the failure message lists which gate rule the
reference violates — fix the reference (in `generate_module.md`) until the
gate is happy. Do not relax the gate.

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/test_ai_prompt_reference_module.py
git commit -m "test(ai): reference support_tickets module passes the gate"
```

---

## Task 4: Skipped-by-default live-API integration test

**Files:**
- Create: `packages/parcel-shell/tests/test_ai_prompt_live_generation.py`

A skip-marked test that hits the live Anthropic API. Documented as a
"run before merge / never in CI" test.

- [ ] **Step 1: Write the test file**

Create `packages/parcel-shell/tests/test_ai_prompt_live_generation.py`:

```python
"""Live-API integration test for the rewritten system prompt.

Skipped by default. To run:

    ANTHROPIC_API_KEY=sk-... uv run pytest \\
        packages/parcel-shell/tests/test_ai_prompt_live_generation.py -v

Costs real Anthropic-API tokens (~30s, ~$0.05). The test asserts the
shape of the generated module — that the discipline rules in the prompt
actually steered the model to:
  - always emit seed.py (Phase 11 follow-up closure),
  - emit dashboards when the user prompt asks for one,
  - emit a workflow with SendEmail + the network capability when asked,
  - never declare filesystem/process/raw_sql.
"""

from __future__ import annotations

import os

import pytest

skip_reason = (
    "needs ANTHROPIC_API_KEY and PARCEL_AI_PROVIDER=api; "
    "intentionally not in CI (real tokens, slow)"
)
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason=skip_reason,
)


@pytest.mark.asyncio
async def test_generated_module_uses_features_when_asked(committing_admin) -> None:
    """End-to-end: the user prompt mentions a dashboard and an email
    workflow; the generated module had better include both."""
    from parcel_shell.ai.generator import generate_module
    from parcel_shell.ai.provider import AnthropicAPIProvider
    from parcel_shell.config import get_settings
    from parcel_shell.db import sessionmaker
    from parcel_shell.app import create_app

    settings = get_settings()
    app = create_app()
    provider = AnthropicAPIProvider(api_key=os.environ["ANTHROPIC_API_KEY"])

    async with sessionmaker()() as db:
        result = await generate_module(
            "Sales-leads CRM. I want a dashboard showing leads by stage. "
            "Send me an email at owner@example.com when a new lead is created.",
            provider=provider,
            db=db,
            app=app,
            settings=settings,
        )
    assert result.kind == "ok", f"generation failed: {result}"

    files = {f.path: f.content for f in result.sandbox.files}
    init_py = next(p for p in files if p.endswith("__init__.py") and "parcel_mod_" in p)

    # Phase-11 follow-up closure: every AI module ships with seed.py.
    assert any(p.endswith("/seed.py") for p in files), "seed.py missing"

    # User asked for both — both should be present.
    assert "dashboards=" in files[init_py]
    assert "workflows=" in files[init_py]

    # SendEmail demands the network capability.
    assert 'capabilities=("network"' in files[init_py]

    # Forbidden caps must not appear, even if model went off-script.
    for forbidden in ("filesystem", "process", "raw_sql"):
        assert forbidden not in files[init_py], (
            f"AI generator must never declare {forbidden!r}"
        )
```

- [ ] **Step 2: Verify the test is collected but skipped without an API key**

Run: `uv run pytest packages/parcel-shell/tests/test_ai_prompt_live_generation.py -v`
Expected: 1 SKIPPED (with the reason text shown).

- [ ] **Step 3: Commit**

```bash
git add packages/parcel-shell/tests/test_ai_prompt_live_generation.py
git commit -m "test(ai): skipped live-API integration for prompt discipline"
```

---

## Task 5: Full verification

- [ ] **Step 1: Run the entire AI test slice**

Run: `uv run pytest packages/parcel-shell/tests/test_ai_*.py -v --tb=short`
Expected: ALL PASS — `test_ai_prompt_shape.py` 7 passed (or however many parametrised), `test_ai_prompt_reference_module.py` 2 passed, `test_ai_prompt_live_generation.py` 1 skipped, plus any pre-existing `test_ai_*.py` files unchanged.

- [ ] **Step 2: Run the full shell test suite**

Run: `uv run pytest packages/parcel-shell/tests/ -v --tb=short`
Expected: ALL PASS — every previous shell test is unaffected. Phase 12 added no shell-runtime code, so zero regressions are expected.

- [ ] **Step 3: Run the full workspace suite**

Run: `uv run pytest`
Expected: PASS, count goes from ~513 to ~516 (3 new tests) with 2 skipped (the existing Phase-11 placeholder + the new live-API one).

- [ ] **Step 4: Lint + types**

Run: `uv run ruff check && uv run ruff format --check && uv run pyright`
Expected: all clean.

- [ ] **Step 5: No commit yet — proceed to docs.**

---

## Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add three new locked-in-decisions rows**

In `CLAUDE.md`, find the last "Sandbox preview *" row (currently:
"Sandbox preview settings | …") and add immediately after it:

```markdown
| AI generator system prompt | Embedded `support_tickets` worked reference module + "Feature menu" discipline section. Single ~750-line prompt loaded for every call (no modular loading). Reference compile-checked against the static-analysis gate via `test_ai_prompt_reference_module.py`. |
| AI feature defaults | `seed.py` always emitted (5–10 records — closes the Phase-11 follow-up). Dashboards default-included when data has obvious aggregations. Reports + workflows only on explicit user request. `Module.preview_routes` never auto-included. |
| AI capability discipline | `network` added iff `SendEmail` / `CallWebhook` is used. `filesystem` / `process` / `raw_sql` never declared by AI generation — the model writes the module without the blocked feature and leaves a `# TODO` comment for the human reviewer instead of refusing entirely. |
```

- [ ] **Step 2: Flip Phase 12 in the roadmap**

In the `## Phased roadmap` table, immediately after the "11" row, add:

```markdown
| 12 | ✅ done | AI generator feature awareness — system prompt teaches dashboards/reports/workflows/seed.py with network-only capability discipline |
```

- [ ] **Step 3: Add a "Phase 12 ✅ shipped" section**

After the `### Phase 11 — Sandbox preview enrichment ✅ shipped` block (and
its known-followups list), insert:

```markdown
### Phase 12 — AI generator feature awareness ✅ shipped

Shipped on the `phase-12-ai-feature-awareness` branch. See the three new "AI generator *" / "AI feature *" / "AI capability *" rows under "Locked-in decisions" for the concrete contracts. Pure prompt rewrite — `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` grew from ~350 to ~750 lines. The new prompt embeds a complete `support_tickets` worked reference module covering dashboards (Phase 8), reports (Phase 9), workflows (Phase 10), and `seed.py` (Phase 11). A new "Feature menu" discipline section tells the model to always emit `seed.py`, default-include dashboards, and only emit workflows / reports on explicit user request. Capabilities are pinned to `network`-only — `filesystem` / `process` / `raw_sql` are never declared; if the user's prompt seems to require them the model writes the module without that feature and leaves a `# TODO` comment for the reviewer.

**Known Phase 12 follow-ups (non-blocking, land opportunistically):**

- **Static-gate enforcement of the AI capability rule.** Today the rule is prompt-only. A small gate addition that bans `filesystem` / `process` / `raw_sql` capabilities on AI-generated sandbox installs would close the loop. Prompts can drift; the gate is the source of truth.
- **Gate awareness of `seed.py`.** Phase 11 left this as a known follow-up. Phase 12 makes `seed.py` ubiquitous, which moves this from "nice-to-have" to "noticeable when it bites."
- **Multi-turn refinement (Phase 13 candidate).** "Now add a workflow that emails me on new ticket" as a follow-up turn that knows the previous draft. Requires accumulating Claude context across turns + the model reading the current sandbox source.
- **Mid-turn `ask_user` (Phase 14 candidate).** A new tool-call type that pauses generation, asks the user a clarifying question with options, resumes with the answer in context.
```

- [ ] **Step 4: Update the "Current phase" prose**

Replace the existing `## Current phase` paragraph (the one starting
"**Phase 11 — Sandbox preview enrichment done.**") with:

```markdown
## Current phase

**Phase 12 — AI generator feature awareness done.** The Claude generator's system prompt now teaches the model every feature the platform exposes — dashboards, reports, workflows, and `seed.py` — anchored on a worked `support_tickets` reference module embedded inline. Three new tests gate the prompt: a static shape check, a reference-module-passes-the-gate check, and a skipped-by-default live-API integration check. AI-generated modules are pinned to `network`-only capability — `filesystem` / `process` / `raw_sql` are never declared, even when the user's prompt seems to require them (the model emits a `# TODO` comment instead of refusing). Pure prompt rewrite — no SDK / shell / migration changes. Test count: ~513 → ~516 (1 new skipped).

Next: **Future** concerns. Phase 12 closes the workflow-and-module-authoring axis. Remaining items (multi-tenancy, OIDC/SAML, module registry, in-browser developer module, non-Python DB) all stay in Future until real users drive prioritisation.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): phase 12 done; locked-in decisions"
```

---

## Task 7: Update website roadmap

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Update the stat-line**

Find the `<div class="stat-line">` (around line 50) and replace the entire
`<div class="stat-line">…</div>` element with:

```html
    <div class="stat-line"><span class="dot"></span> Phases 1–12 complete: shell, auth + RBAC, modules, admin UI, Contacts, SDK + CLI, gate + sandbox, Claude generator + chat, dashboards, reports, workflows (sync triggers, scheduled cron, ARQ worker, retry, send_email/call_webhook/run_module_function/generate_report actions, manual-retry button, audit filters), sandbox preview enrichment (Playwright screenshots, three viewports, optional seed.py), and AI generator feature awareness (the system prompt now teaches dashboards/reports/workflows/seed.py with network-only capability discipline). The workflow-and-module-authoring axis is complete; remaining work is in the Future row.</div>
```

- [ ] **Step 2: Add the Phase 12 row to the roadmap grid**

Find the `<li>` block for Phase 11 (which Phase 11's docs commit set to
`✓ done`). Add a new `<li>` block immediately after Phase 11 and before the
`∞ future` row:

```html
      <li>
        <span class="phase-num">12</span>
        <span class="phase-status done">✓ done</span>
        <span class="phase-goal">AI generator feature awareness — system prompt teaches dashboards/reports/workflows/seed.py with network-only capability</span>
      </li>
```

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "docs(site): phase 12 done in roadmap grid"
```

---

## Task 8: Final verification + PR

- [ ] **Step 1: Final full-suite run**

Run: `uv run pytest`
Expected: PASS — workspace green at ~516 tests with 2 skipped.

- [ ] **Step 2: Final lint + types**

Run: `uv run ruff check && uv run ruff format --check && uv run pyright`
Expected: all clean.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin phase-12-ai-feature-awareness
```

- [ ] **Step 4: Open the PR**

```bash
gh pr create --title "Phase 12: AI generator feature awareness" --body "$(cat <<'EOF'
## Summary

Pure prompt rewrite — `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md` grows from ~350 to ~750 lines. No SDK / shell / migration changes.

**What ships:**
- Embedded `support_tickets` worked reference module covering dashboards (Phase 8), reports (Phase 9), workflows (Phase 10), and `seed.py` (Phase 11). The model pattern-matches against this for structure.
- "Feature menu" discipline section: `seed.py` ALWAYS emitted (closes the Phase-11 follow-up), dashboards default-on when data has aggregations, reports + workflows only on explicit user request.
- Capability discipline: `network` added iff `SendEmail` / `CallWebhook` is used; `filesystem` / `process` / `raw_sql` are never declared by AI generation — the model emits a `# TODO` comment instead of refusing.
- New `shell_api.emit(...)` line in the facade-surface section so workflows actually fire.
- Three new tests: `test_ai_prompt_shape.py` (static markers), `test_ai_prompt_reference_module.py` (extract reference + run through gate), `test_ai_prompt_live_generation.py` (skipped-by-default live-API integration).

**Known follow-ups (non-blocking, documented in CLAUDE.md):**
- Static-gate enforcement of the AI capability rule (today it's prompt-only).
- Gate awareness of `seed.py` (Phase 11 follow-up — now ubiquitous so visibility is up).
- Multi-turn refinement (Phase 13 candidate).
- Mid-turn `ask_user` tool (Phase 14 candidate).

**Test surface:** ~513 → ~516 (1 new skipped).

## Test plan

- [x] `uv run pytest` — workspace green
- [x] `uv run ruff check && uv run ruff format --check` — clean
- [x] `uv run pyright` — 0 errors
- [ ] Manual smoke (with API key): \`ANTHROPIC_API_KEY=sk-... uv run pytest packages/parcel-shell/tests/test_ai_prompt_live_generation.py -v\` — single test passes against a real sandbox
- [ ] Manual: from \`/ai\`, send "CRM with leads-by-stage dashboard and email me on new lead" — observe sandbox detail page shows seeded preview screenshots and dashboard tab

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Squash-merge after review**

Per the validated phase pattern:

```bash
gh pr merge --squash --delete-branch
git checkout main
git pull
```

---

## Self-Review

**Spec coverage** (each spec section / requirement → task):

- Architecture: single-file rewrite of `generate_module.md`, 3 new tests, no SDK changes → Tasks 1–4. ✓
- System prompt structure: 8-section reorganisation → Task 2. ✓
- Worked reference (`support_tickets`): full content for every listed file → Task 2. ✓
- Feature menu (discipline rules): the four-block menu (ALWAYS / DEFAULT / ON REQUEST / NEVER + CAPABILITIES) → Task 2. ✓
- `shell_api.emit` addition to facade surface → Task 2. ✓
- Capability section pinned to network-only → Task 2. ✓
- Test surface: shape test, reference-passes-gate test, skipped live-API test → Tasks 1, 3, 4. ✓
- Failure-modes / drift detection: reference-passes-gate test catches gate evolution → Task 3. ✓
- Locked-in decisions added (3 rows): AI generator system prompt, AI feature defaults, AI capability discipline → Task 6. ✓
- Roadmap flip + Phase 12 shipped section + Current-phase prose → Task 6. ✓
- Website roadmap update → Task 7. ✓
- Out-of-scope deferrals (gate-time enforcement, gate-awareness of seed.py, B/C) → Task 6 follow-ups list. ✓
- Verification gate (pytest + ruff + pyright) → Tasks 5, 8. ✓
- PR + squash-merge → Task 8. ✓

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "fill in details" anywhere in the plan. The two intentional `# TODO` references are inside the discipline rule text the model is instructed to emit (acceptable — that's the reviewer-handoff mechanism, not a plan placeholder).

**Type consistency:**
- `_extract_reference_files` defined in Task 3 returns `dict[str, str]`; consumed by `test_extraction_finds_every_referenced_file` (set comparison) and `test_reference_module_passes_gate` (iteration over items) — both consistent.
- `run_gate(module_root, *, declared_capabilities=frozenset)` matches the actual signature in `parcel_gate.runner` (verified during plan-writing).
- `GateReport.findings` and `GateFinding.severity` matches the existing types (verified — Phase 7a).
- `_HEADING_RE` and `_FENCE_RE` are reused consistently across the extraction.
- The `support_tickets` module's `version="0.1.0"`, `name="support_tickets"`, `len(dashboards)==1`, `len(workflows)==1`, `len(reports)==1`, `workflow_functions=={}`, `capabilities=("network",)` are consistent across `__init__.py` (Task 2), the smoke test (Task 2), and the live-API integration test's expected shape (Task 4).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-phase-12-ai-generator-feature-awareness.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
