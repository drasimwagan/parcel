from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.reports.registry import collect_reports, find_report


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def _report(slug: str = "dir") -> Report:
    return Report(
        slug=slug,
        title="Directory",
        permission="contacts.read",
        template="reports/dir.html",
        data=_data,
        params=_P,
    )


def _app(manifest: dict[str, Module]):
    return SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))


def test_collect_reports_orders_by_module_then_declaration() -> None:
    contacts = Module(name="contacts", version="0.1.0", reports=(_report("a"), _report("b")))
    sales = Module(name="sales", version="0.1.0", reports=(_report("c"),))
    out = collect_reports(_app({"sales": sales, "contacts": contacts}))
    assert [(r.module_name, r.report.slug) for r in out] == [
        ("contacts", "a"),
        ("contacts", "b"),
        ("sales", "c"),
    ]


def test_collect_reports_empty_when_no_state() -> None:
    out = collect_reports(SimpleNamespace(state=SimpleNamespace()))
    assert out == []


def test_find_report_returns_match() -> None:
    contacts = Module(name="contacts", version="0.1.0", reports=(_report("a"),))
    registered = collect_reports(_app({"contacts": contacts}))
    hit = find_report(registered, "contacts", "a")
    assert hit is not None
    assert hit.report.slug == "a"


def test_find_report_returns_none_for_missing() -> None:
    registered = collect_reports(_app({}))
    assert find_report(registered, "contacts", "a") is None
