from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient

from parcel_sdk import EmitAudit, Manual, Module, OnCreate, Workflow
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module

pytestmark = pytest.mark.asyncio


_WF_OK = Workflow(
    slug="welcome",
    title="Welcome",
    permission="users.read",  # admin already has this
    triggers=(OnCreate("demo.thing.created"),),
    actions=(EmitAudit("hi"),),
)
_WF_GATED = Workflow(
    slug="welcome",
    title="Welcome",
    permission="nobody.has.this",
    triggers=(OnCreate("demo.thing.created"),),
    actions=(EmitAudit("hi"),),
)
_WF_MANUAL = Workflow(
    slug="manual",
    title="Manual run",
    permission="users.read",
    triggers=(Manual("demo.manual"),),
    actions=(EmitAudit("manual run"),),
)


def _mount(app: FastAPI, *workflows: Workflow) -> None:
    m = Module(name="demo", version="0.1.0", workflows=workflows)
    mount_module(
        app,
        DiscoveredModule(
            module=m,
            distribution_name="parcel-mod-demo",
            distribution_version="0.1.0",
        ),
    )


@pytest_asyncio.fixture()
async def authed_with_demo_workflow(app: FastAPI, authed_client: AsyncClient):
    _mount(app, _WF_OK)
    return authed_client


async def test_list_logged_out_redirects(client: AsyncClient, app: FastAPI) -> None:
    _mount(app, _WF_OK)
    r = await client.get("/workflows", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


async def test_list_with_visible_workflow(authed_with_demo_workflow: AsyncClient) -> None:
    r = await authed_with_demo_workflow.get("/workflows")
    assert r.status_code == 200
    assert "Welcome" in r.text
    assert "/workflows/demo/welcome" in r.text


async def test_list_hides_workflow_without_permission(
    app: FastAPI, authed_client: AsyncClient
) -> None:
    _mount(app, _WF_GATED)
    r = await authed_client.get("/workflows")
    assert r.status_code == 200
    assert "Welcome" not in r.text


async def test_detail_404_on_missing(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/workflows/nope/none")
    assert r.status_code == 404


async def test_detail_404_on_no_permission(app: FastAPI, authed_client: AsyncClient) -> None:
    _mount(app, _WF_GATED)
    r = await authed_client.get("/workflows/demo/welcome")
    assert r.status_code == 404


async def test_detail_renders_with_permission(authed_with_demo_workflow: AsyncClient) -> None:
    r = await authed_with_demo_workflow.get("/workflows/demo/welcome")
    assert r.status_code == 200
    assert "Welcome" in r.text
    assert "demo.thing.created" in r.text  # trigger summary


async def test_run_404_when_no_manual_trigger(
    authed_with_demo_workflow: AsyncClient,
) -> None:
    r = await authed_with_demo_workflow.post("/workflows/demo/welcome/run")
    assert r.status_code == 404


async def test_run_dispatches_when_manual_trigger(app: FastAPI, authed_client: AsyncClient) -> None:
    _mount(app, _WF_MANUAL)
    r = await authed_client.post("/workflows/demo/manual/run", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/workflows/demo/manual"


# ---- Phase 10c — retry + filter --------------------------------------------


async def _seed_audit_row(
    db_session,
    module: str,
    slug: str,
    status: str,
    event: str = "demo.thing.created",
    attempt: int = 1,
) -> uuid.UUID:
    """Insert a workflow_audit row and return its id."""
    from parcel_shell.workflows.models import WorkflowAudit

    row = WorkflowAudit(
        id=uuid.uuid4(),
        module=module,
        workflow_slug=slug,
        event=event,
        status=status,
        payload={},
        attempt=attempt,
    )
    db_session.add(row)
    await db_session.flush()
    return row.id


async def test_retry_404_on_unknown_audit(authed_client, app: FastAPI) -> None:
    _mount(app, _WF_OK)
    bogus = uuid.uuid4()
    r = await authed_client.post(f"/workflows/demo/welcome/retry/{bogus}")
    assert r.status_code == 404


async def test_retry_404_on_ok_audit(authed_client, app: FastAPI, db_session) -> None:
    _mount(app, _WF_OK)
    aid = await _seed_audit_row(db_session, "demo", "welcome", "ok")
    await db_session.commit()
    r = await authed_client.post(f"/workflows/demo/welcome/retry/{aid}")
    assert r.status_code == 404


async def test_retry_404_when_audit_belongs_to_different_workflow(
    authed_client, app: FastAPI, db_session
) -> None:
    _mount(app, _WF_OK)
    aid = await _seed_audit_row(db_session, "other_module", "other_slug", "error")
    await db_session.commit()
    r = await authed_client.post(f"/workflows/demo/welcome/retry/{aid}")
    assert r.status_code == 404


async def test_retry_303_on_error_audit_inline_mode(
    authed_client, app: FastAPI, db_session
) -> None:
    """Inline mode: retry runs run_workflow directly with attempt+1."""
    _mount(app, _WF_OK)
    aid = await _seed_audit_row(db_session, "demo", "welcome", "error", attempt=1)
    await db_session.commit()
    r = await authed_client.post(f"/workflows/demo/welcome/retry/{aid}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/workflows/demo/welcome"


async def test_detail_filter_status_only_returns_matching(
    authed_client, app: FastAPI, db_session
) -> None:
    _mount(app, _WF_OK)
    await _seed_audit_row(db_session, "demo", "welcome", "ok", event="ev.a")
    await _seed_audit_row(db_session, "demo", "welcome", "error", event="ev.b")
    await db_session.commit()

    r_ok = await authed_client.get("/workflows/demo/welcome?status=ok")
    assert r_ok.status_code == 200
    assert "ev.a" in r_ok.text
    assert "ev.b" not in r_ok.text

    r_err = await authed_client.get("/workflows/demo/welcome?status=error")
    assert "ev.b" in r_err.text
    assert "ev.a" not in r_err.text


async def test_detail_filter_event_substring(authed_client, app: FastAPI, db_session) -> None:
    _mount(app, _WF_OK)
    await _seed_audit_row(db_session, "demo", "welcome", "ok", event="alpha.created")
    await _seed_audit_row(db_session, "demo", "welcome", "ok", event="beta.created")
    await db_session.commit()

    r = await authed_client.get("/workflows/demo/welcome?event=alpha")
    assert r.status_code == 200
    assert "alpha.created" in r.text
    assert "beta.created" not in r.text
