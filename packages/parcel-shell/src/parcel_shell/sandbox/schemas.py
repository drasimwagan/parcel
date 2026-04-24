from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SandboxOut(BaseModel):
    id: UUID
    name: str
    version: str
    declared_capabilities: list[str]
    schema_name: str
    url_prefix: str
    status: str
    gate_report: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    promoted_at: datetime | None = None
    promoted_to_name: str | None = None

    model_config = {"from_attributes": True}


class PromoteIn(BaseModel):
    name: str
    approve_capabilities: list[str] = []


class InstallPathIn(BaseModel):
    path: str
