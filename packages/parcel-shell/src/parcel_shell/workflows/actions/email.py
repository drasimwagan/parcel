"""SendEmail action executor."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Any

from parcel_sdk import SendEmail, WorkflowContext
from parcel_shell.config import Settings, get_settings


async def execute_send_email(
    action: SendEmail, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP not configured (PARCEL_SMTP_HOST is unset)")
    msg = EmailMessage()
    msg["From"] = settings.smtp_from_address or "noreply@parcel.local"
    msg["To"] = action.to
    msg["Subject"] = action.subject
    msg.set_content(action.body)
    await asyncio.to_thread(_smtp_send, msg, settings)
    payload.setdefault("emails_sent", []).append(action.to)


def _smtp_send(msg: EmailMessage, settings: Settings) -> None:
    """Synchronous SMTP send. Called via `asyncio.to_thread` from the executor."""
    with smtplib.SMTP(settings.smtp_host or "", settings.smtp_port) as s:
        if settings.smtp_username:
            s.starttls()
            s.login(settings.smtp_username, settings.smtp_password or "")
        s.send_message(msg)
