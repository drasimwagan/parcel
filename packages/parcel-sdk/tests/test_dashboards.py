from __future__ import annotations

import pytest

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
    with pytest.raises(Exception):
        w.text = "mutated"  # type: ignore[misc]


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
