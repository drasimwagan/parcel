from __future__ import annotations

from parcel_sdk.dashboards import (
    Ctx,
    Dashboard,
    Kpi,
    KpiWidget,
    LineWidget,
    TableWidget,
    scalar_query,
    series_query,
    table_query,
)


async def _total(ctx: Ctx) -> Kpi:
    n = await scalar_query(ctx.session, "SELECT COUNT(*) FROM mod_contacts.contacts")
    return Kpi(value=int(n or 0))


async def _new_this_week(ctx: Ctx) -> Kpi:
    now_n = await scalar_query(
        ctx.session,
        "SELECT COUNT(*) FROM mod_contacts.contacts "
        "WHERE created_at >= NOW() - INTERVAL '7 days'",
    )
    prev_n = await scalar_query(
        ctx.session,
        "SELECT COUNT(*) FROM mod_contacts.contacts "
        "WHERE created_at >= NOW() - INTERVAL '14 days' "
        "  AND created_at <  NOW() - INTERVAL '7 days'",
    )
    now_n = int(now_n or 0)
    prev_n = int(prev_n or 0)
    delta: float | None = None
    if prev_n > 0:
        delta = (now_n - prev_n) / prev_n
    return Kpi(value=now_n, delta=delta, delta_label="vs prior week")


async def _new_30d(ctx: Ctx):
    return await series_query(
        ctx.session,
        """
        SELECT
          to_char(d, 'YYYY-MM-DD') AS day,
          COALESCE(c.n, 0) AS n
        FROM generate_series(
          (CURRENT_DATE - INTERVAL '29 days')::date,
          CURRENT_DATE,
          INTERVAL '1 day'
        ) AS d
        LEFT JOIN (
          SELECT date_trunc('day', created_at)::date AS day, COUNT(*) AS n
          FROM mod_contacts.contacts
          WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
          GROUP BY 1
        ) c ON c.day = d::date
        ORDER BY d
        """,
        label_col="day",
        value_col="n",
    )


async def _recent(ctx: Ctx):
    return await table_query(
        ctx.session,
        """
        SELECT
          (first_name || ' ' || last_name) AS "Name",
          email AS "Email",
          to_char(created_at, 'YYYY-MM-DD HH24:MI') AS "Added"
        FROM mod_contacts.contacts
        ORDER BY created_at DESC
        LIMIT 10
        """,
    )


overview_dashboard = Dashboard(
    name="contacts.overview",
    slug="overview",
    title="Contacts overview",
    permission="contacts.read",
    description="At-a-glance state of your contact list.",
    widgets=(
        KpiWidget(id="total", title="Total contacts", data=_total, col_span=1),
        KpiWidget(id="new_week", title="New this week", data=_new_this_week, col_span=1),
        LineWidget(id="new_30d", title="New contacts (last 30 days)", data=_new_30d, col_span=4),
        TableWidget(id="recent", title="Recently added", data=_recent, col_span=4),
    ),
)
