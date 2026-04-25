from __future__ import annotations

from fastapi import FastAPI

from parcel_sdk import EmitAudit, Module, OnCreate, Permission, Workflow
from parcel_shell.logging import configure_logging
from parcel_shell.modules.discovery import DiscoveredModule
from parcel_shell.modules.integration import mount_module


def test_mount_warns_when_workflow_permission_not_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()

    bad = Workflow(
        slug="welcome",
        title="Welcome",
        permission="contacts.write",  # NOT declared by this module
        triggers=(OnCreate("contacts.contact.created"),),
        actions=(EmitAudit("hi"),),
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        workflows=(bad,),
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
    assert "module.workflow.unknown_permission" in out
    assert "contacts.write" in out


def test_mount_silent_when_workflow_permission_declared(capsys) -> None:
    configure_logging(env="dev", level="WARNING")
    app = FastAPI()
    ok = Workflow(
        slug="welcome",
        title="Welcome",
        permission="contacts.read",
        triggers=(OnCreate("contacts.contact.created"),),
        actions=(EmitAudit("hi"),),
    )
    module = Module(
        name="contacts",
        version="0.1.0",
        permissions=(Permission("contacts.read", "..."),),
        workflows=(ok,),
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
    assert "module.workflow.unknown_permission" not in out
