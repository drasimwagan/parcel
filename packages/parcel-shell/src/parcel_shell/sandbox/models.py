from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from parcel_shell.db import ShellBase

SandboxStatus = Literal["active", "dismissed", "promoted"]


class SandboxInstall(ShellBase):
    __tablename__ = "sandbox_installs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    declared_capabilities: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    schema_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    module_root: Mapped[str] = mapped_column(Text, nullable=False)
    url_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    gate_report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    status: Mapped[SandboxStatus] = mapped_column(Text, nullable=False, default="active")
    promoted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    promoted_to_name: Mapped[str | None] = mapped_column(Text)
