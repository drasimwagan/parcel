from __future__ import annotations

import io
from datetime import UTC, datetime
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse, StreamingResponse

from parcel_sdk import ReportContext
from parcel_sdk.shell_api import Flash
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.reports.forms import render_form
from parcel_shell.reports.pdf import html_to_pdf
from parcel_shell.reports.registry import RegisteredReport, collect_reports, find_report
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

_log = structlog.get_logger("parcel_shell.reports")

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


def _querystring(request: Request) -> str:
    return urlencode({k: v for k, v in dict(request.query_params).items() if v})


async def _render_html_body(
    *, hit: RegisteredReport, params: BaseModel | None, db: AsyncSession, user_id
) -> str:
    ctx = ReportContext(session=db, user_id=user_id, params=params)
    data = await hit.report.data(ctx)
    templates = get_templates()
    template = templates.env.get_template(hit.report.template)
    summary = data.pop("param_summary", None) or _summary(params)
    return template.render(
        report=hit.report,
        generated_at=datetime.now(UTC),
        param_summary=summary,
        **data,
    )


async def _resolve_report_or_404(
    request: Request, module_name: str, slug: str, db: AsyncSession, user_id
) -> tuple[RegisteredReport, set[str]]:
    perms = await service.effective_permissions(db, user_id)
    registered = collect_reports(request.app)
    hit = find_report(registered, module_name, slug)
    if hit is None or hit.report.permission not in perms:
        raise _not_found()
    return hit, perms


@router.get("/{module_name}/{slug}", response_class=HTMLResponse)
async def report_form(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    hit, perms = await _resolve_report_or_404(request, module_name, slug, db, user.id)

    if hit.report.params is None:
        return RedirectResponse(f"/reports/{module_name}/{slug}/render", status_code=303)

    values = _query_dict(request)
    _, errors = _validate_params(hit.report.params, request)
    templates = get_templates()
    if hit.report.form_template is not None:
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


@router.get("/{module_name}/{slug}/render", response_class=HTMLResponse)
async def report_render(
    module_name: str,
    slug: str,
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
):
    hit, perms = await _resolve_report_or_404(request, module_name, slug, db, user.id)
    params, errors = _validate_params(hit.report.params, request)
    templates = get_templates()

    if errors:
        form_html = (
            render_form(hit.report.params, _query_dict(request), errors)
            if hit.report.params is not None
            else ""
        )
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

    try:
        report_html = await _render_html_body(hit=hit, params=params, db=db, user_id=user.id)
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "reports.render_failed",
            module=module_name,
            slug=slug,
            error=str(exc),
        )
        report_html = templates.env.get_template("reports/_error.html").render(
            message="The report could not be rendered."
        )

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
            "querystring": _querystring(request),
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
    hit, _ = await _resolve_report_or_404(request, module_name, slug, db, user.id)
    params, errors = _validate_params(hit.report.params, request)
    if errors:
        target = f"/reports/{module_name}/{slug}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        return RedirectResponse(target, status_code=303)

    try:
        body = await _render_html_body(hit=hit, params=params, db=db, user_id=user.id)
        pdf = await html_to_pdf(body)
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
            Flash(kind="error", msg="Could not generate the PDF. Please try again."),
            secret=request.app.state.settings.session_secret,
        )
        return response

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    filename = f"{module_name}-{slug}-{stamp}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
