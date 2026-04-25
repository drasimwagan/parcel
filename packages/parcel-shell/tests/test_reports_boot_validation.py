from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from parcel_sdk import Module, Permission, Report, ReportContext
from parcel_shell.logging import configure_logging
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


class _P(BaseModel):
    q: str | None = None


async def _data(_ctx: ReportContext) -> dict[str, object]:
    return {}


def test_mount_warns_when_report_permission_not_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()

    bad = Report(
        slug="dir",
        title="Directory",
        permission="contacts.write",  # NOT in module.permissions
        template="reports/x.html",
        data=_data,
        params=_P,
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        reports=(bad,),
    )
    mount_module(
        app,
        DiscoveredModule(
            module=module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        ),
    )
    out = capsys.readouterr().out
    assert "module.report.unknown_permission" in out
    assert "contacts.write" in out


def test_mount_silent_when_report_permission_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()
    ok = Report(
        slug="dir",
        title="Directory",
        permission="contacts.read",
        template="reports/x.html",
        data=_data,
        params=_P,
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        reports=(ok,),
    )
    mount_module(
        app,
        DiscoveredModule(
            module=module,
            distribution_name="parcel-mod-contacts",
            distribution_version="0.1.0",
        ),
    )
    out = capsys.readouterr().out
    assert "module.report.unknown_permission" not in out
