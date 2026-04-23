from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_shell.auth import sessions as sess
from parcel_shell.auth.cookies import sign_session_id, verify_session_cookie
from parcel_shell.auth.dependencies import COOKIE_NAME as SESSION_COOKIE_NAME
from parcel_shell.db import get_session
from parcel_shell.rbac import service
from parcel_shell.ui.dependencies import current_user_html, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import visible_sections
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["ui"])


def _apply_session_cookie(response: Response, *, request: Request, session_id) -> None:
    secret = request.app.state.settings.session_secret
    env = request.app.state.settings.env
    token = sign_session_id(session_id, secret=secret)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(env != "dev"),
        samesite="lax",
        path="/",
    )


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request, next: str | None = None
) -> Response:
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "user": None,
            "sidebar": [],
            "active_path": request.url.path,
            "settings": request.app.state.settings,
            "next_url": next or "/",
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: AsyncSession = Depends(get_session),
) -> Response:
    user = await service.authenticate(db, email=email, password=password)
    if user is None:
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "sidebar": [],
                "active_path": request.url.path,
                "settings": request.app.state.settings,
                "next_url": next,
                "email": email,
                "error": "Invalid email or password.",
            },
            status_code=400,
        )
    s = await sess.create_session(
        db,
        user_id=user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.flush()
    response = RedirectResponse(url=next or "/", status_code=303)
    _apply_session_cookie(response, request=request, session_id=s.id)
    set_flash(
        response,
        Flash(kind="success", msg="Welcome back."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        sid = verify_session_cookie(token, secret=request.app.state.settings.session_secret)
        if sid is not None:
            s = await sess.lookup(db, sid)
            if s is not None:
                await sess.revoke(db, s)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    set_flash(
        response,
        Flash(kind="info", msg="Signed out."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    perms = await service.effective_permissions(db, user.id)
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "sidebar": visible_sections(perms),
            "active_path": request.url.path,
            "settings": request.app.state.settings,
        },
    )


@router.post("/profile/password")
async def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    user=Depends(current_user_html),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await service.change_password(
            db, user=user, current_password=current_password, new_password=new_password
        )
    except service.InvalidCredentials:
        perms = await service.effective_permissions(db, user.id)
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "user": user,
                "sidebar": visible_sections(perms),
                "active_path": "/profile",
                "settings": request.app.state.settings,
                "pw_error": "Current password is incorrect.",
            },
            status_code=400,
        )
    except ValueError as e:
        perms = await service.effective_permissions(db, user.id)
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "profile.html",
            {
                "user": user,
                "sidebar": visible_sections(perms),
                "active_path": "/profile",
                "settings": request.app.state.settings,
                "pw_error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Password changed."),
        secret=request.app.state.settings.session_secret,
    )
    return response
