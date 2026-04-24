from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_sdk.dashboards import (
    BarWidget,
    Dashboard,
    Dataset,
    HeadlineWidget,
    Kpi,
    KpiWidget,
    LineWidget,
    Series,
    Table,
    TableWidget,
    scalar_query,
    series_query,
    table_query,
)


def _kpi_fn(_ctx):  # pragma: no cover - placeholder
    ...


def test_dashboard_basic_construction():
    dash = Dashboard(
        name="contacts.overview",
        slug="overview",
        title="Contacts overview",
        permission="contacts.read",
        widgets=(
            KpiWidget(id="total", title="Total", data=_kpi_fn),
            HeadlineWidget(id="note", title="", text="Hi", col_span=4),
        ),
    )
    assert dash.slug == "overview"
    assert dash.permission == "contacts.read"
    assert len(dash.widgets) == 2
    assert dash.widgets[0].id == "total"


def test_widget_is_frozen():
    w = HeadlineWidget(id="x", title="t", text="hi")
    with pytest.raises(FrozenInstanceError):
        w.text = "mutated"  # type: ignore[misc]


def test_data_is_required_for_data_widgets():
    with pytest.raises(TypeError):
        KpiWidget(id="x", title="t")  # type: ignore[call-arg]


def test_series_and_table_dataclasses():
    s = Series(labels=["a", "b"], datasets=[Dataset(label="count", values=[1, 2])])
    assert s.datasets[0].values == [1, 2]
    t = Table(columns=["a", "b"], rows=[[1, 2], [3, 4]])
    assert t.columns == ["a", "b"]


def test_kpi_optional_delta():
    k = Kpi(value=42)
    assert k.delta is None and k.delta_label is None
    k2 = Kpi(value=42, delta=0.12, delta_label="vs last week")
    assert k2.delta == 0.12


def test_widget_default_col_span_is_two():
    w = HeadlineWidget(id="h", title="t", text="x")
    assert w.col_span == 2


def test_all_chart_widgets_construct():
    async def _fn(_ctx): ...

    assert LineWidget(id="l", title="Line", data=_fn).id == "l"
    assert BarWidget(id="b", title="Bar", data=_fn).id == "b"
    assert TableWidget(id="t", title="Table", data=_fn).id == "t"


async def test_scalar_query_executes_with_params(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash"))
    await pg_session.execute(text("CREATE TABLE t_dash.x (id int primary key, v int)"))
    await pg_session.execute(text("INSERT INTO t_dash.x VALUES (1, 10), (2, 20)"))
    await pg_session.commit()
    n = await scalar_query(pg_session, "SELECT COUNT(*) FROM t_dash.x WHERE v > :min", min=5)
    assert n == 2


async def test_series_query_shapes_result(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash2"))
    await pg_session.execute(text("CREATE TABLE t_dash2.x (label text, v int)"))
    await pg_session.execute(text("INSERT INTO t_dash2.x VALUES ('a', 1), ('b', 2), ('c', 3)"))
    await pg_session.commit()
    s = await series_query(
        pg_session,
        "SELECT label, v FROM t_dash2.x ORDER BY label",
        label_col="label",
        value_col="v",
    )
    assert s.labels == ["a", "b", "c"]
    assert s.datasets[0].values == [1, 2, 3]


async def test_table_query_shapes_rows(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash3"))
    await pg_session.execute(text("CREATE TABLE t_dash3.x (a text, b int)"))
    await pg_session.execute(text("INSERT INTO t_dash3.x VALUES ('x', 1), ('y', 2)"))
    await pg_session.commit()
    t = await table_query(
        pg_session,
        "SELECT a, b FROM t_dash3.x ORDER BY a",
    )
    assert t.columns == ["a", "b"]
    assert t.rows == [["x", 1], ["y", 2]]


async def test_table_query_preserves_columns_on_empty_result(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash_empty"))
    await pg_session.execute(text("CREATE TABLE t_dash_empty.x (a text, b int)"))
    await pg_session.commit()
    t = await table_query(pg_session, "SELECT a, b FROM t_dash_empty.x")
    assert t.columns == ["a", "b"]
    assert t.rows == []


async def test_series_query_coerces_numeric_to_float(pg_session: AsyncSession):
    await pg_session.execute(text("CREATE SCHEMA IF NOT EXISTS t_dash_num"))
    await pg_session.execute(text("CREATE TABLE t_dash_num.x (label text, v numeric)"))
    await pg_session.execute(text("INSERT INTO t_dash_num.x VALUES ('a', 1.5), ('b', 2)"))
    await pg_session.commit()
    s = await series_query(
        pg_session,
        "SELECT label, v FROM t_dash_num.x ORDER BY label",
        label_col="label",
        value_col="v",
    )
    assert s.datasets[0].values == [1.5, 2.0]
    assert all(isinstance(x, float) for x in s.datasets[0].values)
