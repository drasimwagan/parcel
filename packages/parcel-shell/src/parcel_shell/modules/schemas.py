from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ModuleSummary(BaseModel):
    name: str
    version: str
    is_active: bool | None
    is_discoverable: bool
    declared_capabilities: list[str]
    approved_capabilities: list[str]
    schema_name: str | None
    installed_at: datetime | None
    last_migrated_at: datetime | None
    last_migrated_rev: str | None


class InstallModuleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    approve_capabilities: list[str] = Field(default_factory=list)
