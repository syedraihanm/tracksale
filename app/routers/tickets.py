from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.formatting import days_ago, parse_money
from app.models.enums import ISSUE_CATEGORIES, PaymentMode, TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.services.errors import (
    DayClosed,
    DomainError,
    InvalidTransition,
    NeedsConfirmation,
    PinRequired,
    ValidationFailed,
)
from app.services.payments import add_payment, get_ticket_totals
from app.services.receipts import generate_qr_svg, generate_whatsapp_url
from app.services.status import get_allowed_transitions, transition_ticket
from app.services.tickets import (
    clear_ticket_passcode,
    create_ticket,
    delete_ticket,
    reveal_ticket_passcode,
    update_ticket_details,
)
from app.services.warranty import is_under_warranty
from app.templating import templates

router = APIRouter(prefix="/tickets", dependencies=[Depends(require_login)])


@router.get("/new", response_class=HTMLResponse)
def ticket_new(
    request: Request,
    phone: str = Query("", max_length=20),
    name: str = Query("", max_length=100),
    parent: int | None = Query(None),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    # If parent ticket provided for warranty return prefill
    parent_ticket = None
    if parent:
        parent_ticket = db.query(Ticket).filter_by(id=parent, is_deleted=False).first()
        if parent_ticket:
            phone = parent_ticket.customer.phone
            name = parent_ticket.customer.name

    return templates.TemplateResponse(
        request=request,
        name="tickets/new.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "categories": ISSUE_CATEGORIES,
            "prefill_phone": phone,
            "prefill_name": name,
            "parent_ticket": parent_ticket,
        },
    )


@router.post("", dependencies=[Depends(verify_csrf)])
@router.post("/new", dependencies=[Depends(verify_csrf)], include_in_schema=False)
async def ticket_create(
    request: Request,
    customer_phone: str = Form(...),
    customer_name: str = Form(...),
    device_brand: str = Form(...),
    device_model: str = Form(...),
    reported_issue: str | None = Form(None),
    issue_category: str = Form("Other"),
    imei_or_serial: str | None = Form(None),
    color: str | None = Form(None),
    passcode: str | None = Form(None),
    estimate_amount: str | None = Form(None),
    advance_amount: str | None = Form("0"),
    advance_mode: str = Form(PaymentMode.CASH.value),
    advance_note: str | None = Form(None),
    parent_ticket_id: int | None = Form(None),
    # Intake checklist
    screen_cracked: str | None = Form(None),
    powers_on: str | None = Form(None),
    water_damage_indicator: str | None = Form(None),
    back_cover_damaged: str | None = Form(None),
    sim_left: str | None = Form(None),
    memory_card_left: str | None = Form(None),
    charger_accessories_received: str | None = Form(None),
    accessories_note: str | None = Form(None),
    intake_notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    intake_condition = {
        "screen_cracked": screen_cracked == "1",
        "powers_on": powers_on == "1",
        "water_damage_indicator": water_damage_indicator == "1",
        "back_cover_damaged": back_cover_damaged == "1",
        "sim_left": sim_left == "1",
        "memory_card_left": memory_card_left == "1",
        "charger_accessories_received": charger_accessories_received == "1",
        "accessories_note": accessories_note.strip() if accessories_note else "",
        "notes": intake_notes.strip() if intake_notes else "",
    }

    try:
        est = parse_money(estimate_amount) if estimate_amount else None
        adv = parse_money(advance_amount) if advance_amount else 0

        ticket = create_ticket(
            db=db,
            customer_phone=customer_phone,
            customer_name=customer_name,
            device_brand=device_brand,
            device_model=device_model,
            reported_issue=reported_issue,
            issue_category=issue_category,
            imei_or_serial=imei_or_serial,
            color=color,
            passcode=passcode,
            estimate_amount=est,
            intake_condition=intake_condition,
            advance_amount=adv,
            advance_mode=advance_mode,
            advance_note=advance_note,
            parent_ticket_id=parent_ticket_id,
            initial_status=TicketStatus.IN_PROGRESS.value,
        )
        db.commit()
    except DayClosed as e:
        db.rollback()
        return HTMLResponse(
            f'<div class="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm mb-4">'
            f'{e!s} <a href="/cash" class="underline font-bold ml-2">Open Cash Close</a>'
            f'</div>',
            status_code=422,
        )
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        return HTMLResponse(
            f'<div class="p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm mb-4">{e!s}</div>',
            status_code=422,
        )

    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{id}", response_class=HTMLResponse)
def ticket_detail(request: Request, id: int, db: Session = Depends(get_db)):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    ticket = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.customer),
            joinedload(Ticket.items),
            joinedload(Ticket.payments),
            joinedload(Ticket.status_histories),
            joinedload(Ticket.parent_ticket),
            joinedload(Ticket.child_tickets),
        )
        .filter(Ticket.id == id)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    customer_total, net_paid, balance_due = get_ticket_totals(ticket)
    allowed_transitions = get_allowed_transitions(ticket.status)
    under_w = is_under_warranty(ticket)

    # Sort status histories newest first
    histories = sorted(ticket.status_histories, key=lambda h: h.changed_at, reverse=True)

    # WhatsApp URLs
    wa_intake = generate_whatsapp_url(
        ticket=ticket,
        template_text=setting.msg_template_intake if setting else "",
        shop_name=setting.shop_name if setting else "Mobile Repair Shop",
    )
    wa_ready = generate_whatsapp_url(
        ticket=ticket,
        template_text=setting.msg_template_ready if setting else "",
        shop_name=setting.shop_name if setting else "Mobile Repair Shop",
    )

    # Non-deleted items
    visible_items = [i for i in ticket.items if not i.is_deleted]
    item_cost_total = sum(i.cost_price for i in visible_items)
    # Payments list: keep all but flag deleted
    payments_list = sorted(ticket.payments, key=lambda p: p.paid_at, reverse=True)

    # Fetch audit log for this ticket
    from app.models.audit_log import AuditLog
    audits = (
        db.query(AuditLog)
        .filter(AuditLog.ticket_id == ticket.id)
        .order_by(AuditLog.timestamp.desc())
        .limit(50)
        .all()
    )

    from app.services.inventory import get_available_spares
    from app.services.suppliers import list_suppliers
    available_inventory = get_available_spares(db)
    active_suppliers = list_suppliers(db, active_only=True)

    context_data = {
        "session": session,
        "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
        "ticket": ticket,
        "age_days": days_ago(ticket.received_at),
        "items_total": customer_total,
        "customer_total": customer_total,
        "customer_total_set": customer_total > 0,
        "item_cost_total": item_cost_total,
        "net_paid": net_paid,
        "balance_due": balance_due,
        "allowed_transitions": allowed_transitions,
        "under_warranty": under_w,
        "histories": histories,
        "visible_items": visible_items,
        "payments_list": payments_list,
        "audits": audits,
        "wa_intake_url": wa_intake,
        "wa_ready_url": wa_ready,
        "categories": ISSUE_CATEGORIES,
        "available_inventory": available_inventory,
        "suppliers": active_suppliers,
    }

    if request.headers.get("HX-Request") == "true" and request.query_params.get("drawer") == "1":
        return templates.TemplateResponse(
            request=request,
            name="partials/ticket_drawer.html",
            context=context_data,
        )

    return templates.TemplateResponse(
        request=request,
        name="tickets/detail.html",
        context=context_data,
    )


@router.post("/{id}/edit", dependencies=[Depends(verify_csrf)])
def ticket_edit(
    request: Request,
    id: int,
    device_brand: str = Form(...),
    device_model: str = Form(...),
    reported_issue: str | None = Form(None),
    issue_category: str = Form(...),
    imei_or_serial: str | None = Form(None),
    color: str | None = Form(None),
    estimate_amount: str | None = Form(None),
    technician_note: str | None = Form(None),
    screen_cracked: str | None = Form(None),
    powers_on: str | None = Form(None),
    water_damage_indicator: str | None = Form(None),
    back_cover_damaged: str | None = Form(None),
    sim_left: str | None = Form(None),
    memory_card_left: str | None = Form(None),
    charger_accessories_received: str | None = Form(None),
    accessories_note: str | None = Form(None),
    intake_notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    condition = {
        "screen_cracked": screen_cracked == "1",
        "powers_on": powers_on == "1",
        "water_damage_indicator": water_damage_indicator == "1",
        "back_cover_damaged": back_cover_damaged == "1",
        "sim_left": sim_left == "1",
        "memory_card_left": memory_card_left == "1",
        "charger_accessories_received": charger_accessories_received == "1",
        "accessories_note": accessories_note.strip() if accessories_note else "",
        "notes": intake_notes.strip() if intake_notes else "",
    }

    try:
        est = parse_money(estimate_amount) if estimate_amount else None
        update_ticket_details(
            db=db,
            ticket=ticket,
            device_brand=device_brand,
            device_model=device_model,
            reported_issue=reported_issue,
            issue_category=issue_category,
            imei_or_serial=imei_or_serial,
            color=color,
            estimate_amount=est,
            technician_note=technician_note,
            intake_condition=condition,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url=f"/tickets/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/status", dependencies=[Depends(verify_csrf)])
def ticket_change_status(
    request: Request,
    id: int,
    to_status: str = Form(...),
    note: str | None = Form(None),
    confirm_pending_balance: str | None = Form("0"),
    clear_passcode: str | None = Form("0"),
    delivery_payment_amount: str | None = Form(None),
    delivery_payment_mode: str = Form("cash"),
    delivery_payment_note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    ticket = (
        db.query(Ticket)
        .options(joinedload(Ticket.items), joinedload(Ticket.payments))
        .filter_by(id=id, is_deleted=False)
        .first()
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        if delivery_payment_amount and delivery_payment_amount.strip():
            if to_status != "delivered":
                raise ValidationFailed("A delivery payment can only be recorded while delivering the ticket")

            payment_amount = parse_money(delivery_payment_amount)
            _, _, balance_due = get_ticket_totals(ticket)
            if balance_due > 0 and payment_amount > balance_due:
                raise ValidationFailed("Delivery payment cannot exceed the balance due")

            add_payment(
                db=db,
                ticket=ticket,
                amount=payment_amount,
                mode=delivery_payment_mode,
                kind="final",
                note=delivery_payment_note,
            )

        transition_ticket(
            db=db,
            ticket=ticket,
            to_status=to_status,
            note=note,
            confirm_pending_balance=confirm_pending_balance == "1",
            clear_passcode=clear_passcode == "1",
        )
        db.commit()
    except InvalidTransition as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except NeedsConfirmation as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DomainError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/delete", dependencies=[Depends(verify_csrf)])
def ticket_soft_delete(
    request: Request,
    id: int,
    reason: str = Form(...),
    owner_pin: str = Form(...),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        delete_ticket(db, ticket, reason=reason, owner_pin=owner_pin)
        db.commit()
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/passcode/reveal", dependencies=[Depends(verify_csrf)])
@router.post("/{id}/reveal-passcode", dependencies=[Depends(verify_csrf)], include_in_schema=False)
def ticket_reveal_passcode(request: Request, id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    plain = reveal_ticket_passcode(db, ticket)
    db.commit()
    return HTMLResponse(f'<span class="font-mono text-sm font-bold text-slate-900 bg-slate-100 px-2 py-1 rounded">{plain or "None"}</span>')


@router.post("/{id}/passcode/clear", dependencies=[Depends(verify_csrf)])
def ticket_clear_passcode(request: Request, id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    clear_ticket_passcode(db, ticket)
    db.commit()
    return HTMLResponse('<span class="text-xs text-slate-400 italic">Passcode cleared</span>')


@router.get("/{id}/receipt", response_class=HTMLResponse)
def ticket_receipt(request: Request, id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter_by(id=id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    setting = db.query(SettingsModel).filter_by(id=1).first()
    session = get_current_session(request)

    customer_total, net_paid, balance_due = get_ticket_totals(ticket)
    qr_svg = generate_qr_svg(ticket.ticket_no)

    wa_url = generate_whatsapp_url(
        ticket=ticket,
        template_text=setting.msg_template_intake if setting else "",
        shop_name=setting.shop_name if setting else "Mobile Repair Shop",
    )

    return templates.TemplateResponse(
        request=request,
        name="tickets/receipt.html",
        context={
            "session": session,
            "setting": setting,
            "ticket": ticket,
            "items_total": customer_total,
            "customer_total": customer_total,
            "customer_total_set": customer_total > 0,
            "net_paid": net_paid,
            "balance_due": balance_due,
            "qr_svg": qr_svg,
            "whatsapp_url": wa_url,
        },
    )
