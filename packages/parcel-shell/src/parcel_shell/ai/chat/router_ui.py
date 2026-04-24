from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.ai.chat import service as chat_service
from parcel_shell.ai.chat.worker import run_turn
from parcel_shell.db import get_session
from parcel_shell.rbac import service as rbac_service
from parcel_shell.ui.dependencies import html_require_permission
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui", "ai-chat"])


async def _ctx(
    request: Request, user: Any, db: AsyncSession, path: str
) -> dict[str, Any]:
    perms = await rbac_service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": sidebar_for(request, perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


def _any_generating(turns) -> bool:
    return any(t.status == "generating" for t in turns)


@router.get("/ai", response_class=HTMLResponse)
async def ai_sessions_list(
    request: Request,
    user=Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    sessions = await chat_service.list_sessions_for_owner(db, user.id)
    # Count turns per session in a single pass (small N).
    counts: dict = {}
    for s in sessions:
        counts[s.id] = await chat_service.count_session_turns(db, s.id)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "ai/list.html",
        {
            **(await _ctx(request, user, db, "/ai")),
            "sessions": sessions,
            "turn_counts": counts,
        },
    )


@router.post("/ai/sessions")
async def ai_session_create(
    request: Request,
    user=Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    s = await chat_service.create_session(db, owner_id=user.id)
    return RedirectResponse(url=f"/ai/sessions/{s.id}", status_code=303)


@router.get("/ai/sessions/{sid}", response_class=HTMLResponse)
async def ai_session_detail(
    sid: UUID,
    request: Request,
    user=Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    session_row = await chat_service.get_session(db, sid, owner_id=user.id)
    if session_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    turns = await chat_service.get_turns(db, sid)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "ai/detail.html",
        {
            **(await _ctx(request, user, db, "/ai")),
            "session": session_row,
            "turns": turns,
            "polling": _any_generating(turns),
            "provider_configured": getattr(
                request.app.state, "ai_provider", None
            )
            is not None,
        },
    )


@router.post("/ai/sessions/{sid}/turns")
async def ai_session_add_turn(
    sid: UUID,
    request: Request,
    prompt: str = Form(...),
    user=Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    session_row = await chat_service.get_session(db, sid, owner_id=user.id)
    if session_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")

    turn = await chat_service.add_turn(db, sid, prompt.strip())
    await db.commit()

    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        async with request.app.state.sessionmaker() as task_db:
            await chat_service.mark_failed(
                task_db,
                turn.id,
                kind="provider_error",
                message="AI provider not configured",
            )
            await task_db.commit()
    else:
        task = asyncio.create_task(
            run_turn(
                turn_id=turn.id,
                prompt=prompt.strip(),
                provider=provider,
                sessionmaker=request.app.state.sessionmaker,
                app=request.app,
                settings=request.app.state.settings,
            )
        )
        tasks: set = getattr(request.app.state, "ai_tasks", set())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        request.app.state.ai_tasks = tasks

    return RedirectResponse(url=f"/ai/sessions/{sid}", status_code=303)


@router.get("/ai/sessions/{sid}/status", response_class=HTMLResponse)
async def ai_session_status_fragment(
    sid: UUID,
    request: Request,
    user=Depends(html_require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    session_row = await chat_service.get_session(db, sid, owner_id=user.id)
    if session_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session_not_found")
    turns = await chat_service.get_turns(db, sid)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "ai/_turns.html",
        {
            "session": session_row,
            "turns": turns,
            "polling": _any_generating(turns),
        },
    )
