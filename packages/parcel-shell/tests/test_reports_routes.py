from __future__ import annotations

from typing import Any

import jinja2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module

pytestmark = pytest.mark.asyncio


def _weasyprint_loadable() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        return False
    return True


class _Params(BaseModel):
    q: str | None = None
    n: int = 0


async def _data_ok(ctx: ReportContext) -> dict[str, Any]:
    q = getattr(ctx.params, "q", None)
    return {"items": ["alpha", "beta"], "param_summary": f"q={q}"}


async def _data_boom(_ctx: ReportContext) -> dict[str, Any]:
    raise RuntimeError("data fn exploded")


async def _data_no_params(_ctx: ReportContext) -> dict[str, Any]:
    return {"items": []}


def _module(report: Report) -> Module:
    return Module(name="demo", version="0.1.0", reports=(report,))


_REPORT_OK = Report(
    slug="dir",
    title="Demo report",
    permission="users.read",
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


def _ensure_demo_template(app: FastAPI) -> None:
    """Inject a demo template into the loader so tests don't need a real package."""
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
    assert 'name="n"' in r.text


async def test_report_render_success(authed_with_demo_report: AsyncClient) -> None:
    r = await authed_with_demo_report.get("/reports/demo/dir/render?q=alice")
    assert r.status_code == 200
    assert "alpha" in r.text and "beta" in r.text
    assert 'id="report-content"' in r.text


async def test_report_render_failure_shows_error_block(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _REPORT_BOOM)
    _ensure_demo_template(app)
    r = await authed_client.get("/reports/demo/dir/render?q=x")
    assert r.status_code == 200
    assert "could not be rendered" in r.text.lower()


@pytest.mark.skipif(not _weasyprint_loadable(), reason="WeasyPrint native libs not available")
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
