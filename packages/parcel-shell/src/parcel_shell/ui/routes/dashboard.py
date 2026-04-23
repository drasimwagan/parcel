from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    perms = await service.effective_permissions(db, user.id)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "sidebar": sidebar_for(request, perms),
            "active_path": "/",
            "settings": request.app.state.settings,
            "permissions": perms,
        },
    )
