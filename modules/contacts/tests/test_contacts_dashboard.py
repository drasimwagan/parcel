from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_sdk.dashboards import Ctx, Kpi, Series, Table

pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession, n_now: int = 3, n_old: int = 2) -> None:
    now = datetime.now(tz=UTC)
    for i in range(n_now):
        await session.execute(
            text(
                "INSERT INTO mod_contacts.contacts "
                "(id, first_name, last_name, email, created_at, updated_at) "
                "VALUES (:id, :f, :l, :e, :c, :c)"
            ),
            {"id": uuid4(), "f": f"F{i}", "l": f"L{i}", "e": f"x{i}@e.com", "c": now},
        )
    for i in range(n_old):
        await session.execute(
            text(
                "INSERT INTO mod_contacts.contacts "
                "(id, first_name, last_name, email, created_at, updated_at) "
                "VALUES (:id, :f, :l, :e, :c, :c)"
            ),
            {
                "id": uuid4(),
                "f": f"O{i}",
                "l": f"O{i}",
                "e": f"o{i}@e.com",
                "c": now - timedelta(days=40),
            },
        )
    await session.commit()


@pytest.fixture()
def ctx(contacts_session: AsyncSession) -> Ctx:
    return Ctx(session=contacts_session, user_id=uuid4())


async def test_overview_dashboard_declaration() -> None:
    assert overview_dashboard.slug == "overview"
    assert overview_dashboard.permission == "contacts.read"
    ids = [w.id for w in overview_dashboard.widgets]
    assert ids == ["total", "new_week", "new_30d", "recent"]


async def test_total_kpi(ctx: Ctx, contacts_session: AsyncSession) -> None:
    await _seed(contacts_session, n_now=3, n_old=2)
    w = next(w for w in overview_dashboard.widgets if w.id == "total")
    kpi: Kpi = await w.data(ctx)
    assert kpi.value == 5


async def test_new_week_kpi(ctx: Ctx, contacts_session: AsyncSession) -> None:
    await _seed(contacts_session, n_now=3, n_old=2)
    w = next(w for w in overview_dashboard.widgets if w.id == "new_week")
    kpi: Kpi = await w.data(ctx)
    assert kpi.value == 3


async def test_new_30d_series(ctx: Ctx, contacts_session: AsyncSession) -> None:
    await _seed(contacts_session, n_now=3, n_old=0)
    w = next(w for w in overview_dashboard.widgets if w.id == "new_30d")
    series: Series = await w.data(ctx)
    assert sum(series.datasets[0].values) == 3


async def test_recent_table(ctx: Ctx, contacts_session: AsyncSession) -> None:
    await _seed(contacts_session, n_now=3, n_old=0)
    w = next(w for w in overview_dashboard.widgets if w.id == "recent")
    tbl: Table = await w.data(ctx)
    assert tbl.columns == ["Name", "Email", "Added"]
    assert len(tbl.rows) == 3
