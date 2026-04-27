from __future__ import annotations

from pathlib import Path

from parcel_mod_contacts import (
    seed,  # noqa: F401  -- seed_runner discovers via getattr(loaded, "seed")
)
from parcel_mod_contacts.dashboards import overview_dashboard
from parcel_mod_contacts.models import metadata
from parcel_mod_contacts.reports import directory_report
from parcel_mod_contacts.router import router
from parcel_mod_contacts.sidebar import SIDEBAR_ITEMS
from parcel_mod_contacts.workflows import (
    audit_log,
    audit_log_via_function,
    daily_audit_summary,
    welcome_workflow,
)
from parcel_sdk import Module, Permission

module = Module(
    name="contacts",
    version="0.7.0",
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
    workflows=(welcome_workflow, daily_audit_summary, audit_log_via_function),
    workflow_functions={"audit_log": audit_log},
)

__all__ = ["module"]
