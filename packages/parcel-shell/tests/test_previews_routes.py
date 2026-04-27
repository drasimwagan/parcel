from __future__ import annotations

import pytest
from fastapi import APIRouter
from sqlalchemy import Column, MetaData, String, Table, text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk import Module, PreviewRoute
from parcel_shell.sandbox.previews import routes


def _make_module_with_router(routes_to_add: list[tuple[str, str]]) -> Module:
    """Build a synthetic Module whose router carries the given (path, methods) routes."""
    r = APIRouter()
    for path, _ in routes_to_add:

        async def _h() -> dict:
            return {}

        r.add_api_route(path, _h, methods=["GET"])
    return Module(name="t", version="0.1.0", router=r)


@pytest.mark.asyncio
async def test_resolve_auto_walks_no_path_params(db_session: AsyncSession) -> None:
    m = _make_module_with_router([("/a", "GET"), ("/b", "GET")])
    paths = await routes.resolve(m, db_session, "public")
    assert paths == ["/a", "/b"]


@pytest.mark.asyncio
async def test_resolve_skips_post_only(db_session: AsyncSession) -> None:
    r = APIRouter()

    async def _h() -> dict:
        return {}

    r.add_api_route("/a", _h, methods=["GET"])
    r.add_api_route("/b", _h, methods=["POST"])
    m = Module(name="t", version="0.1.0", router=r)
    paths = await routes.resolve(m, db_session, "public")
    assert paths == ["/a"]


@pytest.mark.asyncio
async def test_resolve_path_params_substituted_from_table(
    db_session: AsyncSession,
) -> None:
    md = MetaData(schema="shell")  # any existing schema
    Table(
        "sandbox_installs",  # reuse existing table for live data lookup
        md,
        Column("id", String, primary_key=True),
        Column("name", String),
        extend_existing=True,
    )
    # Insert a row we can fabricate {id} from.
    await db_session.execute(
        text(
            "INSERT INTO shell.sandbox_installs (id, name, version, declared_capabilities, "
            "schema_name, module_root, url_prefix, gate_report, created_at, expires_at) "
            "VALUES (:id, 'x', '0.1.0', '[]'::jsonb, 'mod_x', '/tmp/x', '/x', '{}'::jsonb, "
            "now(), now())"
        ),
        {"id": "00000000-0000-0000-0000-000000000099"},
    )
    r = APIRouter()

    async def _h(id: str) -> dict:
        return {}

    r.add_api_route("/things/{id}", _h, methods=["GET"])
    m = Module(name="t", version="0.1.0", router=r, metadata=md)
    paths = await routes.resolve(m, db_session, "shell")
    assert paths == ["/things/00000000-0000-0000-0000-000000000099"]


@pytest.mark.asyncio
async def test_resolve_skips_unresolvable_path_param(db_session: AsyncSession) -> None:
    r = APIRouter()

    async def _h(unknown: str) -> dict:
        return {}

    r.add_api_route("/x/{unknown}", _h, methods=["GET"])
    m = Module(name="t", version="0.1.0", router=r, metadata=MetaData())
    paths = await routes.resolve(m, db_session, "public")
    assert paths == []


@pytest.mark.asyncio
async def test_resolve_uses_preview_routes_override(db_session: AsyncSession) -> None:
    r = APIRouter()

    async def _h() -> dict:
        return {}

    r.add_api_route("/a", _h, methods=["GET"])
    r.add_api_route("/b", _h, methods=["GET"])
    m = Module(
        name="t",
        version="0.1.0",
        router=r,
        preview_routes=(PreviewRoute(path="/b"),),
    )
    paths = await routes.resolve(m, db_session, "public")
    assert paths == ["/b"]


@pytest.mark.asyncio
async def test_resolve_calls_explicit_params_callable(db_session: AsyncSession) -> None:
    async def _params(_session: AsyncSession) -> dict[str, str]:
        return {"id": "abc"}

    r = APIRouter()

    async def _h(id: str) -> dict:
        return {}

    r.add_api_route("/x/{id}", _h, methods=["GET"])
    m = Module(
        name="t",
        version="0.1.0",
        router=r,
        preview_routes=(PreviewRoute(path="/x/{id}", params=_params),),
    )
    paths = await routes.resolve(m, db_session, "public")
    assert paths == ["/x/abc"]
