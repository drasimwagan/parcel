"""GenerateReport action executor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from parcel_sdk import GenerateReport, ReportContext, WorkflowContext


async def execute_generate_report(
    action: GenerateReport, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    """Render a Phase-9 report's HTML body and stash in `payload.reports`."""
    from parcel_shell.reports.registry import collect_reports, find_report
    from parcel_shell.ui.templates import get_templates
    from parcel_shell.workflows.runner import _active_app

    if _active_app is None:
        raise RuntimeError("GenerateReport: shell not initialised")
    registered = collect_reports(_active_app)
    hit = find_report(registered, action.module, action.slug)
    if hit is None:
        raise RuntimeError(f"GenerateReport: {action.module}.{action.slug} not found")
    report = hit.report
    params_obj = None
    if report.params is not None:
        params_obj = report.params.model_validate(action.params or {})
    rctx = ReportContext(session=ctx.session, user_id=ctx.subject_id, params=params_obj)
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
        {
            "module": action.module,
            "slug": action.slug,
            "report_html": rendered[:32_768],
        }
    )
