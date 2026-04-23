from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse, RedirectResponse

from parcel_mod_contacts import service
from parcel_shell.db import get_session
from parcel_shell.rbac import service as rbac_service
from parcel_shell.ui.dependencies import html_require_permission, set_flash
from parcel_shell.ui.flash import Flash
from parcel_shell.ui.sidebar import sidebar_for
from parcel_shell.ui.templates import get_templates

router = APIRouter(tags=["mod-contacts"])


async def _ctx(request: Request, user, db: AsyncSession, path: str) -> dict:
    perms = await rbac_service.effective_permissions(db, user.id)
    return {
        "user": user,
        "sidebar": sidebar_for(request, perms),
        "active_path": path,
        "settings": request.app.state.settings,
    }


# ── Contacts ────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def contacts_list(
    request: Request,
    q: str | None = None,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contacts, _ = await service.list_contacts(db, q=q)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "contacts/list.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts")),
            "contacts": contacts,
            "q": q,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def contacts_new_form(
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    companies, _ = await service.list_companies(db, limit=500)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "contacts/new.html",
        {**(await _ctx(request, user, db, "/mod/contacts")), "companies": companies},
    )


@router.post("/")
async def contacts_create(
    request: Request,
    email: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    phone: str = Form(""),
    company_id: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    cid = uuid.UUID(company_id) if company_id else None
    try:
        new = await service.create_contact(
            db,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            company_id=cid,
        )
    except Exception as e:  # noqa: BLE001
        companies, _ = await service.list_companies(db, limit=500)
        tpl = get_templates()
        return tpl.TemplateResponse(
            request,
            "contacts/new.html",
            {
                **(await _ctx(request, user, db, "/mod/contacts")),
                "companies": companies,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url=f"/mod/contacts/{new.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created {new.email}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/{contact_id}", response_class=HTMLResponse)
async def contacts_detail(
    contact_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    companies, _ = await service.list_companies(db, limit=500)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "contacts/detail.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts")),
            "contact": contact,
            "companies": companies,
        },
    )


@router.post("/{contact_id}/edit")
async def contacts_edit(
    contact_id: uuid.UUID,
    request: Request,
    email: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    phone: str = Form(""),
    company_id: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    if company_id:
        await service.update_contact(
            db,
            contact=contact,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            company_id=uuid.UUID(company_id),
        )
    else:
        await service.update_contact(
            db,
            contact=contact,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            clear_company=True,
        )
    response = RedirectResponse(url=f"/mod/contacts/{contact_id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Contact saved."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/{contact_id}/delete")
async def contacts_delete(
    contact_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    contact = await service.get_contact(db, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "contact_not_found")
    await service.delete_contact(db, contact=contact)
    response = RedirectResponse(url="/mod/contacts/", status_code=303)
    set_flash(
        response,
        Flash(kind="info", msg="Contact deleted."),
        secret=request.app.state.settings.session_secret,
    )
    return response


# ── Companies ──────────────────────────────────────────────────────────


@router.get("/companies", response_class=HTMLResponse)
async def companies_list(
    request: Request,
    q: str | None = None,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    companies, _ = await service.list_companies(db, q=q)
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "companies/list.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts/companies")),
            "companies": companies,
            "q": q,
        },
    )


@router.get("/companies/new", response_class=HTMLResponse)
async def companies_new_form(
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "companies/new.html",
        await _ctx(request, user, db, "/mod/contacts/companies"),
    )


@router.post("/companies")
async def companies_create(
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    try:
        new = await service.create_company(db, name=name, website=website)
    except Exception as e:  # noqa: BLE001
        tpl = get_templates()
        return tpl.TemplateResponse(
            request,
            "companies/new.html",
            {
                **(await _ctx(request, user, db, "/mod/contacts/companies")),
                "name": name,
                "website": website,
                "error": str(e),
            },
            status_code=400,
        )
    response = RedirectResponse(url=f"/mod/contacts/companies/{new.id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg=f"Created {new.name}"),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def companies_detail(
    company_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.read")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    tpl = get_templates()
    return tpl.TemplateResponse(
        request,
        "companies/detail.html",
        {
            **(await _ctx(request, user, db, "/mod/contacts/companies")),
            "company": company,
        },
    )


@router.post("/companies/{company_id}/edit")
async def companies_edit(
    company_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    website: str = Form(""),
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    await service.update_company(db, company=company, name=name, website=website)
    response = RedirectResponse(url=f"/mod/contacts/companies/{company_id}", status_code=303)
    set_flash(
        response,
        Flash(kind="success", msg="Company saved."),
        secret=request.app.state.settings.session_secret,
    )
    return response


@router.post("/companies/{company_id}/delete")
async def companies_delete(
    company_id: uuid.UUID,
    request: Request,
    user=Depends(html_require_permission("contacts.write")),
    db: AsyncSession = Depends(get_session),
) -> Response:
    company = await service.get_company(db, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company_not_found")
    await service.delete_company(db, company=company)
    response = RedirectResponse(url="/mod/contacts/companies", status_code=303)
    set_flash(
        response,
        Flash(kind="info", msg="Company deleted."),
        secret=request.app.state.settings.session_secret,
    )
    return response
