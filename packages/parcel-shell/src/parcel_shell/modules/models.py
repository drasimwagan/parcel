from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from parcel_shell.db import ShellBase


class InstalledModule(ShellBase):
    __tablename__ = "installed_modules"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    capabilities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    schema_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    installed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    last_migrated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_migrated_rev: Mapped[str | None] = mapped_column(Text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "is_active": self.is_active,
            "capabilities": list(self.capabilities or []),
            "schema_name": self.schema_name,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
            "last_migrated_at": self.last_migrated_at,
            "last_migrated_rev": self.last_migrated_rev,
        }
