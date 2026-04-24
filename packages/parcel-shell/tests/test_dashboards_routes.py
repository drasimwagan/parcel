from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

from parcel_sdk import Dashboard, HeadlineWidget, Kpi, KpiWidget, Module
from parcel_sdk.dashboards import Ctx
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module

pytestmark = pytest.mark.asyncio


async def _kpi_greet(_ctx: Ctx) -> Kpi:
    return Kpi(value="hello")


async def _kpi_fail(_ctx: Ctx) -> Kpi:
    raise RuntimeError("boom")


DEMO_DASHBOARD = Dashboard(
    name="demo.overview",
    slug="overview",
    title="Demo overview",
    permission="users.read",  # admin already has this
    widgets=(
        KpiWidget(id="greet", title="Greeting", data=_kpi_greet),
        HeadlineWidget(id="note", title="", text="Hi", col_span=4),
    ),
)

GATED_DASHBOARD = Dashboard(
    name="demo.overview",
    slug="overview",
    title="Demo overview",
    permission="nobody.has.this",
    widgets=(HeadlineWidget(id="h", title="", text="x"),),
)

FAILING_DASHBOARD = Dashboard(
    name="demo.overview",
    slug="overview",
    title="T",
    permission="users.read",
    widgets=(KpiWidget(id="bad", title="Bad", data=_kpi_fail),),
)


def _mount(app: FastAPI, dashboards: tuple[Dashboard, ...]) -> None:
    m = Module(name="demo", version="0.1.0", dashboards=dashboards)
    mount_module(
        app,
        DiscoveredModule(
            module=m,
            distribution_name="parcel-mod-demo",
            distribution_version="0.1.0",
        ),
    )


@pytest_asyncio.fixture()
async def authed_client_with_demo_dashboard(app: FastAPI, authed_client: AsyncClient):
    _mount(app, (DEMO_DASHBOARD,))
    return authed_client


@pytest_asyncio.fixture()
async def authed_client_with_gated_dashboard(app: FastAPI, authed_client: AsyncClient):
    _mount(app, (GATED_DASHBOARD,))
    return authed_client


@pytest_asyncio.fixture()
async def authed_client_with_failing_widget(app: FastAPI, authed_client: AsyncClient):
    _mount(app, (FAILING_DASHBOARD,))
    return authed_client


async def test_list_empty_when_no_dashboards(authed_client: AsyncClient):
    resp = await authed_client.get("/dashboards")
    assert resp.status_code == 200
    assert "No dashboards" in resp.text


async def test_list_redirects_when_unauthenticated(client: AsyncClient):
    resp = await client.get("/dashboards", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


async def test_detail_404_on_unknown(authed_client: AsyncClient):
    resp = await authed_client.get("/dashboards/missing/overview")
    assert resp.status_code == 404


async def test_detail_renders_with_mounted_dashboard(
    authed_client_with_demo_dashboard: AsyncClient,
):
    resp = await authed_client_with_demo_dashboard.get("/dashboards/demo/overview")
    assert resp.status_code == 200
    assert 'hx-get="/dashboards/demo/overview/widgets/greet"' in resp.text


async def test_detail_404_when_user_lacks_permission(
    authed_client_with_gated_dashboard: AsyncClient,
):
    resp = await authed_client_with_gated_dashboard.get("/dashboards/demo/overview")
    assert resp.status_code == 404


async def test_widget_kpi_renders_value(authed_client_with_demo_dashboard: AsyncClient):
    resp = await authed_client_with_demo_dashboard.get(
        "/dashboards/demo/overview/widgets/greet"
    )
    assert resp.status_code == 200
    assert "hello" in resp.text


async def test_widget_404_on_missing_widget(authed_client_with_demo_dashboard: AsyncClient):
    resp = await authed_client_with_demo_dashboard.get(
        "/dashboards/demo/overview/widgets/nope"
    )
    assert resp.status_code == 404


async def test_widget_error_partial_on_raise(
    authed_client_with_failing_widget: AsyncClient,
):
    resp = await authed_client_with_failing_widget.get(
        "/dashboards/demo/overview/widgets/bad"
    )
    assert resp.status_code == 200
    assert "Couldn't load this widget" in resp.text
