from __future__ import annotations

from pathlib import Path

from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_mod_contacts.models import metadata
from parcel_mod_contacts.reports import directory_report
from parcel_mod_contacts.router import router
from parcel_mod_contacts.sidebar import SIDEBAR_ITEMS
from parcel_mod_contacts.workflows import daily_audit_summary, welcome_workflow
from parcel_sdk import Module, Permission

module = Module(
    name="contacts",
    version="0.5.0",
    permissions=(
        Permission("contacts.read", "View contacts and companies"),
        Permission("contacts.write", "Create, update, and delete contacts and companies"),
    ),
    capabilities=(),
    alembic_ini=Path(__file__).parent / "alembic.ini",
    metadata=metadata,
    router=router,
    templates_dir=Path(__file__).parent / "templates",
    sidebar_items=SIDEBAR_ITEMS,
    dashboards=(overview_dashboard,),
    reports=(directory_report,),
    workflows=(welcome_workflow, daily_audit_summary),
)

__all__ = ["module"]
