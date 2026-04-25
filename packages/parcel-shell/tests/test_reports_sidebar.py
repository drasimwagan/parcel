from __future__ import annotations

from types import SimpleNamespace

from pydantic import BaseModel

from parcel_sdk import Module, Report, ReportContext
from parcel_shell.ui.sidebar import _reports_section


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def _report(slug: str, title: str, perm: str) -> Report:
    return Report(
        slug=slug,
        title=title,
        permission=perm,
        template="reports/x.html",
        data=_data,
        params=_P,
    )


def _request(manifest: dict[str, Module]):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(active_modules_manifest=manifest))
    )


def test_reports_section_visible_with_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(_report("dir", "Directory", "contacts.read"),),
    )
    section = _reports_section(_request({"contacts": contacts}), {"contacts.read"})
    assert section is not None
    assert section.label == "Reports"
    assert [item.label for item in section.items] == ["Contacts: Directory"]


def test_reports_section_hidden_without_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(_report("dir", "Directory", "contacts.read"),),
    )
    section = _reports_section(_request({"contacts": contacts}), set())
    assert section is None


def test_reports_section_hidden_when_no_reports() -> None:
    contacts = Module(name="contacts", version="0.1.0")
    section = _reports_section(_request({"contacts": contacts}), {"users.read"})
    assert section is None


def test_reports_section_filters_per_report_permission() -> None:
    contacts = Module(
        name="contacts",
        version="0.1.0",
        reports=(
            _report("dir", "Directory", "contacts.read"),
            _report("priv", "Private", "secret.read"),
        ),
    )
    section = _reports_section(_request({"contacts": contacts}), {"contacts.read"})
    assert section is not None
    assert [i.label for i in section.items] == ["Contacts: Directory"]
