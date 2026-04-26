"""CallWebhook action executor."""

from __future__ import annotations

from typing import Any

import httpx

from parcel_sdk import CallWebhook, WorkflowContext


async def execute_call_webhook(
    action: CallWebhook, ctx: WorkflowContext, payload: dict[str, Any]
) -> None:
    """Send an HTTP request and capture the response status + truncated body."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            action.method,
            action.url,
            headers=action.headers,
            json=action.body,
        )
    resp.raise_for_status()
    payload.setdefault("webhook_calls", []).append(
        {"url": action.url, "status": resp.status_code, "body": resp.text[:1024]}
    )
