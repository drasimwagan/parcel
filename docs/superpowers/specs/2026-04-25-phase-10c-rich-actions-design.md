# Phase 10c — Workflows rich actions + UI

**Status:** approved
**Date:** 2026-04-25
**Builds on:** Phase 10b-retry (workflow engine + ARQ + retry semantics).

## Goal

Add four new action types (`SendEmail`, `CallWebhook`, `RunModuleFunction`, `GenerateReport`), per-action capability declarations with mount-time warnings, an audit filter UI on the workflow detail page, and a manual-retry route + button. Contacts gains a reference `audit_log_via_function` workflow demonstrating `RunModuleFunction`.

## Non-goals (10c)

- **HTML email / attachments.** Plain text only; modules wanting HTML write a custom function.
- **Webhook signing / HMAC.** Plain HTTP POST; modules add their own auth via `headers`.
- **PDF generation as an action.** `GenerateReport` produces HTML in the audit payload; PDF rendering is heavyweight and lands in Phase 11+.
- **AI-generator capability gate.** Mount-time warns; AI-generator-time validation lands when Phase 11 wires AI generation through workflows.
- **State-machine "running instances" UI.** Workflows are still chains.
- **Per-recipient retry on partial email failures.** `SendEmail` is one recipient per action; multi-recipient is a list-of-actions concern.
- **Bulk retry / DLQ UI.** Manual retry is one row at a time.

## Locked decisions

| Area | Decision |
|---|---|
| New action types | `SendEmail`, `CallWebhook`, `RunModuleFunction`, `GenerateReport`. All frozen kw_only SDK dataclasses. |
| `SendEmail` | Args: `to: str`, `subject: str`, `body: str`. Uses stdlib `smtplib.SMTP` in `asyncio.to_thread`. Settings: `PARCEL_SMTP_HOST`, `_PORT` (default 587), `_USERNAME`, `_PASSWORD`, `_FROM_ADDRESS`. If `smtp_host` is None, action raises `RuntimeError("SMTP not configured")`. Required capability: `network`. |
| `CallWebhook` | Args: `url: str`, `method: str = "POST"`, `headers: dict[str, str] = {}`, `body: dict[str, Any] \| None = None`. Uses `httpx.AsyncClient(timeout=30.0)`. Non-2xx response raises. Audit payload captures `status_code` and (truncated) response body. Required capability: `network`. |
| `RunModuleFunction` | Args: `module: str`, `function: str`. Looks up `app.state.active_modules_manifest[module].workflow_functions[function]` at run time. Awaits with `WorkflowContext`. Return value coerced to `str(ret)[:1024]` and stored in `payload.return_value`. Required capability: `None` (module's own code paths). |
| `GenerateReport` | Args: `module: str`, `slug: str`, `params: dict[str, Any] = {}`. Resolves the report via `parcel_shell.reports.registry.find_report`. Validates `params` against `Report.params` Pydantic model (if any). Calls `report.data(ReportContext(...))`. Renders `report.template` extending `_report_base.html` to a string. Stores in `payload.report_html` (truncated to 32 KiB). Required capability: `None`. |
| `SendEmail` body interpolation | None for 10c — `subject` and `body` are static strings on the dataclass. Templating (Jinja against `subject`/`event`) lands in 10c follow-up if needed. |
| Capability ClassVar | Each action class has `_required_capability: ClassVar[str \| None]`. `SendEmail._required_capability = "network"`, `CallWebhook._required_capability = "network"`, others `None`. |
| Mount-time capability warning | New helper in `parcel_shell/modules/integration.py`: walks each declared workflow's actions, collects their `_required_capability` values, warns `module.workflow.missing_capability` if the value isn't in `Module.capabilities`. Doesn't block — same model as the existing `unknown_permission` warnings. |
| Module workflow functions | New SDK field `Module.workflow_functions: dict[str, Callable[[WorkflowContext], Awaitable[Any]]] = {}`. `RunModuleFunction` looks up by name. |
| Manual-retry route | `POST /workflows/<module>/<slug>/retry/<audit_id>`. Permission-gated. Looks up the audit row by id; rejects (404) if missing or `status="ok"` (only failed attempts retry). Builds an event dict with the original `event` and `subject_id`, re-fetches the subject if `subject_id` is present, runs `dispatch_events(...)` for inline mode OR enqueues a `run_event_dispatch` ARQ job for queued mode. New audit row with `attempt = original.attempt + 1`. Returns 303 to the detail page with a flash. |
| Audit filter | Detail page query string: `?status=ok\|error&event=...`. Server-side WHERE clauses on the existing audits select. The detail template renders a small filter form above the audits table (status select + event text input + Apply / Clear). |
| `Retry` button | Inline `<form method="post" action="/workflows/<m>/<s>/retry/<a.id>">` rendered next to each errored audit row. Hidden for `status="ok"` rows. |
| SDK version | 0.8.0 → **0.9.0**. |
| Contacts version | 0.5.0 → **0.6.0**. Adds `audit_log` to `Module.workflow_functions` + a `audit_log_via_function` workflow on `OnCreate("contacts.contact.created")`. |
| New shell runtime dep | `httpx>=0.27,<1.0` (already a dev dep; promote to runtime). |
| New tests | ~25. SDK (5), action execution (8), capability warning (2), routes (5), contacts reference (3), e2e via testcontainer Redis (1), retry flow (1). |

## Architecture

```
parcel_sdk/
  workflows.py                   # adds SendEmail, CallWebhook, RunModuleFunction, GenerateReport, _required_capability ClassVars
  module.py                      # adds workflow_functions field
parcel_shell/
  workflows/
    actions/                     # NEW package
      __init__.py
      email.py                   # _execute_send_email + smtp send (sync, run_in_executor)
      webhook.py                 # _execute_call_webhook (httpx)
      module_function.py         # _execute_run_module_function
      report.py                  # _execute_generate_report (uses parcel_shell.reports)
    runner.py                    # execute_action gains dispatch for new types via the actions package
    router.py                    # adds POST /retry/<audit_id> + audit-filter query params
    templates/workflows/
      detail.html                # audit filter form + Retry button
  config.py                      # SMTP settings
  modules/integration.py         # mount-time capability warning
modules/contacts/src/parcel_mod_contacts/
  workflows.py                   # add audit_log_via_function workflow
  __init__.py                    # add workflow_functions={"audit_log": ...}; bump to 0.6.0
```

## SDK changes

```python
# parcel_sdk/workflows.py — adds:

from collections.abc import Awaitable, Callable
from typing import Any, ClassVar


@dataclass(frozen=True)
class SendEmail:
    """Send a plain-text email via the shell's configured SMTP host.

    Required capability: `network`.
    """

    to: str
    subject: str
    body: str
    _required_capability: ClassVar[str | None] = "network"


@dataclass(frozen=True)
class CallWebhook:
    """POST (or other HTTP) a JSON body to a URL.

    Required capability: `network`.
    """

    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    _required_capability: ClassVar[str | None] = "network"


@dataclass(frozen=True)
class RunModuleFunction:
    """Invoke a function the module declared in `Module.workflow_functions`."""

    module: str
    function: str
    _required_capability: ClassVar[str | None] = None


@dataclass(frozen=True)
class GenerateReport:
    """Render a Phase-9 report's HTML body and store it in the audit payload."""

    module: str
    slug: str
    params: dict[str, Any] = field(default_factory=dict)
    _required_capability: ClassVar[str | None] = None


Action = (
    UpdateField | EmitAudit | SendEmail | CallWebhook | RunModuleFunction | GenerateReport
)
```

`Module.workflow_functions: dict[str, Callable[[WorkflowContext], Awaitable[Any]]] = field(default_factory=dict)` — added to the `Module` dataclass with type-only forward reference.

## Action execution

The runner's `execute_action` gains a dispatch table for the new types via small helpers in the `actions/` package:

```python
# parcel_shell/workflows/actions/email.py

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any

from parcel_sdk import SendEmail, WorkflowContext
from parcel_shell.config import get_settings


async def execute_send_email(
    action: SendEmail, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP not configured (PARCEL_SMTP_HOST is unset)")
    msg = EmailMessage()
    msg["From"] = settings.smtp_from_address or "noreply@parcel.local"
    msg["To"] = action.to
    msg["Subject"] = action.subject
    msg.set_content(action.body)
    await asyncio.to_thread(_smtp_send, msg, settings)
    payload.setdefault("emails_sent", []).append(action.to)


def _smtp_send(msg, settings) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        if settings.smtp_username:
            s.starttls()
            s.login(settings.smtp_username, settings.smtp_password or "")
        s.send_message(msg)
```

```python
# parcel_shell/workflows/actions/webhook.py

import httpx

from parcel_sdk import CallWebhook, WorkflowContext


async def execute_call_webhook(
    action: CallWebhook, ctx: WorkflowContext, payload: dict
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            action.method,
            action.url,
            headers=action.headers,
            json=action.body,
        )
    resp.raise_for_status()  # non-2xx → HTTPStatusError → audited as error
    payload.setdefault("webhook_calls", []).append(
        {"url": action.url, "status": resp.status_code, "body": resp.text[:1024]}
    )
```

```python
# parcel_shell/workflows/actions/module_function.py

from parcel_sdk import RunModuleFunction, WorkflowContext
from parcel_shell.workflows.runner import _active_app


async def execute_run_module_function(
    action: RunModuleFunction, ctx: WorkflowContext, payload: dict
) -> None:
    manifest = getattr(_active_app.state, "active_modules_manifest", {})
    module = manifest.get(action.module)
    if module is None:
        raise RuntimeError(f"RunModuleFunction: module {action.module!r} not active")
    fn = getattr(module, "workflow_functions", {}).get(action.function)
    if fn is None:
        raise RuntimeError(
            f"RunModuleFunction: {action.module}.{action.function} not registered"
        )
    ret = await fn(ctx)
    payload.setdefault("function_calls", []).append(
        {"module": action.module, "function": action.function, "return": str(ret)[:1024]}
    )
```

```python
# parcel_shell/workflows/actions/report.py

from datetime import UTC, datetime

from parcel_sdk import GenerateReport, ReportContext, WorkflowContext
from parcel_shell.reports.registry import collect_reports, find_report
from parcel_shell.ui.templates import get_templates
from parcel_shell.workflows.runner import _active_app


async def execute_generate_report(
    action: GenerateReport, ctx: WorkflowContext, payload: dict
) -> None:
    registered = collect_reports(_active_app)
    hit = find_report(registered, action.module, action.slug)
    if hit is None:
        raise RuntimeError(f"GenerateReport: {action.module}.{action.slug} not found")
    report = hit.report
    params_obj = None
    if report.params is not None:
        params_obj = report.params.model_validate(action.params or {})
    rctx = ReportContext(
        session=ctx.session, user_id=ctx.subject_id, params=params_obj
    )
    data = await report.data(rctx)
    summary = data.pop("param_summary", None) or "scheduled"
    templates = get_templates()
    template = templates.env.get_template(report.template)
    rendered = template.render(
        report=report,
        generated_at=datetime.now(UTC),
        param_summary=summary,
        **data,
    )
    payload.setdefault("reports", []).append(
        {"module": action.module, "slug": action.slug, "report_html": rendered[:32_768]}
    )
```

`runner.execute_action` extends the existing `isinstance` chain to dispatch to these helpers. `UpdateField` and `EmitAudit` paths unchanged.

## Capability mount-time warning

```python
# parcel_shell/modules/integration.py — adds (inside mount_module, after the existing report-permission check):

declared_caps = set(getattr(discovered.module, "capabilities", ()))
for workflow in getattr(discovered.module, "workflows", ()):
    for action in workflow.actions:
        cap = getattr(type(action), "_required_capability", None)
        if cap and cap not in declared_caps:
            _log.warning(
                "module.workflow.missing_capability",
                module=name,
                slug=workflow.slug,
                action=type(action).__name__,
                capability=cap,
            )
```

## SMTP settings

```python
# parcel_shell/config.py — adds to Settings:

smtp_host: str | None = Field(default=None, alias="PARCEL_SMTP_HOST")
smtp_port: int = Field(default=587, alias="PARCEL_SMTP_PORT")
smtp_username: str | None = Field(default=None, alias="PARCEL_SMTP_USERNAME")
smtp_password: str | None = Field(default=None, alias="PARCEL_SMTP_PASSWORD")
smtp_from_address: str | None = Field(default=None, alias="PARCEL_SMTP_FROM_ADDRESS")
```

## Manual-retry route

```python
# parcel_shell/workflows/router.py — adds:

@router.post("/{module_name}/{slug}/retry/{audit_id}")
async def workflow_retry(
    module_name: str,
    slug: str,
    audit_id: uuid.UUID,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    perms = await service.effective_permissions(db, user.id)
    registered = collect_workflows(request.app)
    hit = find_workflow(registered, module_name, slug)
    if hit is None or hit.workflow.permission not in perms:
        raise _not_found()

    audit = await db.get(WorkflowAudit, audit_id)
    if audit is None or audit.module != module_name or audit.workflow_slug != slug:
        raise _not_found()
    if audit.status == "ok":
        # Don't retry successful invocations.
        raise _not_found()

    sessionmaker = request.app.state.sessionmaker
    next_attempt = audit.attempt + 1
    ev = {
        "event": audit.event,
        "subject": None,
        "subject_id": audit.subject_id,
        "changed": (),
    }
    # Re-fetch subject if we have an id and the workflow's actions need one.
    # (This is best-effort; UpdateField will fail if class can't be resolved.)
    inline = bool(os.environ.get("PARCEL_WORKFLOWS_INLINE"))
    if inline:
        await run_workflow(module_name, hit.workflow, ev, sessionmaker, attempt=next_attempt)
    else:
        from parcel_shell.workflows.serialize import encode_events

        await request.app.state.arq_redis.enqueue_job(
            "run_event_dispatch", encode_events([ev]), _job_try=next_attempt
        )

    response = RedirectResponse(f"/workflows/{module_name}/{slug}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Retrying attempt {next_attempt}…"),
        secret=request.app.state.settings.session_secret,
    )
    return response
```

Note: re-enqueueing with `_job_try=next_attempt` requires ARQ to honor the kwarg. ARQ's `enqueue_job` doesn't expose `_job_try` directly — instead we accept that retry from the manual button passes `attempt=next_attempt` to the inline path, and for the queued path we trust the worker to start at `job_try=1`. In practice this means the manual-retry audit row in queued mode shows `attempt=1` (a fresh ARQ job try) regardless of the original audit's attempt. This is acceptable — manual retries are user-driven; the chronological audit ordering still tells the story. Documented in the spec's "Risks" section.

## Audit filter

```python
# parcel_shell/workflows/router.py — workflow_detail handler updates:

@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def workflow_detail(
    module_name: str,
    slug: str,
    request: Request,
    status: str | None = None,        # NEW
    event: str | None = None,         # NEW
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    # ... existing permission check ...

    stmt = (
        select(WorkflowAudit)
        .where(
            WorkflowAudit.module == module_name,
            WorkflowAudit.workflow_slug == slug,
        )
        .order_by(desc(WorkflowAudit.created_at))
        .limit(50)
    )
    if status in ("ok", "error"):
        stmt = stmt.where(WorkflowAudit.status == status)
    if event:
        stmt = stmt.where(WorkflowAudit.event.ilike(f"%{event}%"))

    audits = (await db.scalars(stmt)).all()
    # ... pass `status` and `event` to the template for form pre-fill ...
```

`detail.html` template additions:

```html
<form method="get" class="mb-2 flex gap-2 text-sm">
  <select name="status" class="border rounded px-2">
    <option value="">All statuses</option>
    <option value="ok" {% if request.query_params.get('status') == 'ok' %}selected{% endif %}>OK</option>
    <option value="error" {% if request.query_params.get('status') == 'error' %}selected{% endif %}>Error</option>
  </select>
  <input type="text" name="event" value="{{ request.query_params.get('event', '') }}"
         placeholder="event substring" class="border rounded px-2 flex-1">
  <button type="submit" class="px-3 py-1 rounded bg-indigo-600 text-white">Apply</button>
  <a href="/workflows/{{ module_name }}/{{ workflow.slug }}" class="px-3 py-1 rounded border">Clear</a>
</form>
```

Plus a per-row Retry button when `audit.status == "error"`:

```html
<td class="p-2">
  {% if a.status == "error" %}
    <form method="post" action="/workflows/{{ module_name }}/{{ workflow.slug }}/retry/{{ a.id }}" style="display:inline;">
      <button type="submit" class="text-xs underline text-indigo-600">Retry</button>
    </form>
  {% endif %}
</td>
```

(New "Actions" column at the right of the audits table.)

## Reference workflow — Contacts `audit_log_via_function`

```python
# modules/contacts/src/parcel_mod_contacts/workflows.py — adds:

from parcel_sdk import RunModuleFunction


async def audit_log(ctx: WorkflowContext) -> str:
    """Toy module function — logs the event name and returns a short token."""
    return f"logged-{ctx.event}-{ctx.subject_id}"


audit_log_via_function = Workflow(
    slug="audit_log_via_function",
    title="Run audit_log function on create",
    permission="contacts.read",
    triggers=(OnCreate("contacts.contact.created"),),
    actions=(RunModuleFunction(module="contacts", function="audit_log"),),
)
```

`__init__.py` adds:

```python
workflow_functions={"audit_log": audit_log},
```

(Module bumps to `0.6.0`.)

## Tests

Target: ~25 new (~460 total).

**SDK** (`packages/parcel-sdk/tests/test_workflows.py` extension)
- Each new action class is frozen + has the right kw_only/positional shape (5 tests).
- `_required_capability` ClassVars correct (`"network"` for Send/Webhook, `None` for the others).

**Action execution**
- `SendEmail` raises when `smtp_host` is None; smtp send succeeds with a mock SMTP class (2).
- `CallWebhook` posts JSON body, audit captures status code + truncated response (2).
- `CallWebhook` raises on 5xx response (1).
- `RunModuleFunction` invokes the registered fn; missing module/function raises (3).
- `GenerateReport` resolves a report and renders HTML into payload (1); missing report raises (1).

**Capability warning** (`test_workflows_boot_validation.py` extension)
- Workflow declaring `CallWebhook` action with `network` capability declared → no warning.
- Workflow declaring `SendEmail` without `network` capability → `module.workflow.missing_capability` warned.

**Routes** (`test_workflows_routes.py` extension)
- `/retry/<audit_id>` 404 on unknown audit; 404 cross-workflow audit; 404 on `status=ok` audit; 303 + flash on retryable audit (4).
- Audit filter renders only matching rows (1).

**Contacts integration** (`test_contacts_router.py` extension)
- `audit_log_via_function` workflow appears in manifest.
- Creating a contact fires both welcome (existing) and audit_log workflows; audit rows for both.

**E2E retry through manual button** (testcontainer redis)
- POST `/retry/<id>` re-enqueues; worker burst-runs; new audit row appears.

## Documentation

- `docs/module-authoring.md` "Workflows" section: a new "Action library" subsection covering all four new action types, capability requirements, examples (each with a real-world use case).
- `CLAUDE.md`: flip 10c → ✅; locked-decisions block; current-phase paragraph; next-phase pointer (Phase 11).
- `docs/index.html`: 10c done; 11 next.

## Migration / compatibility

- No new shell migrations.
- SDK 0.9.0 — additive: existing `Workflow(...)` and `Module(...)` calls keep working.
- New shell runtime dep: `httpx>=0.27,<1.0`. Already a workspace dev dep — promoting to runtime is a one-line change.
- New optional settings (`PARCEL_SMTP_*`). All default to None/sane defaults; no `.env` changes required to boot.

## Risks and follow-ups

- **Manual retry doesn't preserve `attempt` numbering through ARQ.** The queued path enqueues a fresh job whose `job_try` starts at 1; the resulting audit row shows `attempt=1` regardless of what the original was. Inline path correctly uses `attempt=audit.attempt+1`. Acceptable; chronological ordering on the detail page still tells the retry story. A 10c follow-up could add an explicit `original_audit_id` linking column on the audit table.
- **`SendEmail` runs SMTP synchronously in a thread.** For high volumes, this becomes a bottleneck. Defer until measured; modules with high email volume can use `RunModuleFunction` to call a custom SES/Mailgun integration.
- **`CallWebhook` has no signing / HMAC.** Modules that need authenticated webhooks pass `headers={"Authorization": "Bearer ..."}`. HMAC signing is a 10c follow-up if a real use case appears.
- **`GenerateReport` payload is truncated to 32 KiB.** Reports larger than that get clipped silently. Acceptable for audit-log purposes; modules wanting full reports use `RunModuleFunction` to call Playwright + email-attach.
- **Mount-time capability warnings don't enforce.** Same model as the existing permission warnings — log + continue. AI-generator-time enforcement lands in Phase 11.
- **`RunModuleFunction` accepts arbitrary callables.** A buggy module function can take down the worker for that one job. The runner's existing try/except + audit-on-error still catches it; just the audit message will be the function's exception text.

## Open during implementation

None.
