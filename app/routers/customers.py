from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.formatting import normalize_phone
from app.models.customer import Customer
from app.models.settings import Settings as SettingsModel
from app.services.customers import get_customer_summary, update_customer_notes
from app.services.warranty import is_under_warranty
from app.templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/customers/lookup", response_class=HTMLResponse)
def lookup_customer(request: Request, phone: str = Query("", max_length=20), db: Session = Depends(get_db)):
    """Intake live customer lookup by phone."""
    try:
        clean_phone = normalize_phone(phone)
    except ValueError:
        return HTMLResponse('<div class="text-xs text-slate-400 mt-1">Enter a valid 10-digit phone number</div>')

    customer = db.query(Customer).filter_by(phone=clean_phone).first()
    if not customer:
        return HTMLResponse(
            '<div class="text-xs text-emerald-600 font-medium flex items-center gap-1 mt-1">'
            '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>'
            'New customer'
            '</div>'
        )

    # Existing customer: gather past tickets (max 5)
    past_tickets = [t for t in customer.tickets if not t.is_deleted]
    past_tickets.sort(key=lambda x: x.received_at, reverse=True)
    recent = past_tickets[:5]

    ticket_summaries = []
    has_active_warranty = False
    for t in recent:
        under_w = is_under_warranty(t)
        if under_w:
            has_active_warranty = True
        ticket_summaries.append({
            "ticket": t,
            "under_warranty": under_w,
        })

    return templates.TemplateResponse(
        request=request,
        name="partials/customer_lookup_result.html",
        context={
            "customer": customer,
            "past_tickets": ticket_summaries,
            "has_active_warranty": has_active_warranty,
        },
    )


@router.get("/customers/{id}", response_class=HTMLResponse)
def customer_detail(request: Request, id: int, db: Session = Depends(get_db)):
    summary = get_customer_summary(db, id)
    if not summary:
        raise HTTPException(status_code=404, detail="Customer not found")

    setting = db.query(SettingsModel).filter_by(id=1).first()
    session = get_current_session(request)

    return templates.TemplateResponse(
        request=request,
        name="customers/detail.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "customer": summary["customer"],
            "tickets": summary["tickets"],
            "total_spent": summary["total_spent"],
        },
    )


@router.post("/customers/{id}", dependencies=[Depends(verify_csrf)])
def customer_update_notes(request: Request, id: int, notes: str = Form(""), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter_by(id=id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    update_customer_notes(db, customer, notes)
    db.commit()

    if request.headers.get("HX-Request") == "true":
        return Response(
            content='<div class="text-xs text-emerald-600 mt-1 font-medium">Notes saved successfully.</div>',
            headers={"HX-Trigger": '{"toast": {"message": "Customer notes updated"}}'},
        )
    return RedirectResponse(url=f"/customers/{id}", status_code=303)
