from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.deps import get_current_session, require_login
from app.formatting import days_ago
from app.models.enums import TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.services.payments import get_ticket_totals
from app.services.receipts import generate_whatsapp_url
from app.templating import templates
from app.timeutil import (
    utc_now,
)

router = APIRouter(dependencies=[Depends(require_login)])

STATUS_ORDER = [
    TicketStatus.RECEIVED.value,
    TicketStatus.AWAITING_APPROVAL.value,
    TicketStatus.IN_PROGRESS.value,
    TicketStatus.AWAITING_PARTS.value,
    TicketStatus.READY_FOR_PICKUP.value,
    TicketStatus.DECLINED.value,
    TicketStatus.UNREPAIRABLE.value,
    TicketStatus.DELIVERED.value,
]

STATUS_DISPLAY_NAMES = {
    TicketStatus.RECEIVED.value: "Received",
    TicketStatus.AWAITING_APPROVAL.value: "Awaiting Approval",
    TicketStatus.IN_PROGRESS.value: "In Progress",
    TicketStatus.AWAITING_PARTS.value: "Awaiting Parts",
    TicketStatus.READY_FOR_PICKUP.value: "Ready for Pickup",
    TicketStatus.DECLINED.value: "Declined (To Hand Back)",
    TicketStatus.UNREPAIRABLE.value: "Unrepairable (To Hand Back)",
    TicketStatus.DELIVERED.value: "Delivered (Last 30 Days)",
}


@router.get("/", response_class=HTMLResponse)
@router.get("/queue", response_class=HTMLResponse, include_in_schema=False)
def queue_view(
    request: Request,
    status: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    """Grouped table ticket queue view."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    now = utc_now()
    active_defaults = [s for s in STATUS_ORDER if s != TicketStatus.DELIVERED.value]

    # Check whether the request has explicit filter parameters
    is_filtering = "status" in request.query_params or "filtered" in request.query_params
    if is_filtering:
        selected_statuses = [s for s in status if s in STATUS_ORDER]
    else:
        selected_statuses = active_defaults

    # Query active tickets
    query = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.customer),
            joinedload(Ticket.items),
            joinedload(Ticket.payments),
            joinedload(Ticket.status_histories),
        )
        .filter(Ticket.is_deleted.is_(False))
    )

    if not selected_statuses:
        tickets = []
    elif TicketStatus.DELIVERED.value in selected_statuses:
        # If delivered is selected, restrict delivered tickets to last 30 days
        thirty_days_ago = now - timedelta(days=30)
        query = query.filter(
            Ticket.status.in_(selected_statuses),
            or_(
                Ticket.status != TicketStatus.DELIVERED.value,
                Ticket.delivered_at >= thirty_days_ago,
                Ticket.delivered_at.is_(None),
            ),
        )
        tickets = query.order_by(desc(Ticket.received_at)).all()
    else:
        query = query.filter(Ticket.status.in_(selected_statuses))
        tickets = query.order_by(desc(Ticket.received_at)).all()

    # Group tickets by status order
    grouped: dict[str, list[dict]] = {s: [] for s in STATUS_ORDER if s in selected_statuses}

    for t in tickets:
        if t.status not in grouped:
            continue
        items_total, net_paid, balance_due = get_ticket_totals(t)
        age_days = days_ago(t.received_at, now_dt=now)

        # In status days from latest status history
        histories = [h for h in t.status_histories if h.to_status == t.status]
        latest_hist = max(histories, key=lambda h: h.changed_at) if histories else None
        in_status_days = days_ago(latest_hist.changed_at if latest_hist else t.received_at, now_dt=now)

        grouped[t.status].append({
            "ticket": t,
            "items_total": items_total,
            "net_paid": net_paid,
            "balance_due": balance_due,
            "age_days": age_days,
            "in_status_days": in_status_days,
            "is_stale_7d": in_status_days > 7 and t.status != TicketStatus.DELIVERED.value,
        })

    # Prepare group cards in standard order
    groups_data = []
    for s in STATUS_ORDER:
        if s in grouped:
            groups_data.append({
                "status": s,
                "display_name": STATUS_DISPLAY_NAMES.get(s, s),
                "items": grouped[s],
                "tickets": grouped[s],
                "count": len(grouped[s]),
            })

    total_count = sum(g["count"] for g in groups_data)

    context = {
        "request": request,
        "session": session,
        "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
        "groups": groups_data,
        "total_count": total_count,
        "all_statuses": STATUS_ORDER,
        "status_display_names": STATUS_DISPLAY_NAMES,
        "selected_statuses": selected_statuses,
    }

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(request=request, name="partials/queue_table.html", context=context)

    return templates.TemplateResponse(request=request, name="queue/index.html", context=context)


@router.get("/ready", response_class=HTMLResponse)
def ready_list(request: Request, db: Session = Depends(get_db)):
    """List of tickets ready for pickup, sorted by days waiting descending."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()
    now = utc_now()

    tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.customer),
            joinedload(Ticket.items),
            joinedload(Ticket.payments),
        )
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.status == TicketStatus.READY_FOR_PICKUP.value,
        )
        .all()
    )

    enriched = []
    for t in tickets:
        _, _, balance_due = get_ticket_totals(t)
        waiting_days = days_ago(t.ready_at or t.received_at, now_dt=now)
        wa_url = generate_whatsapp_url(
            ticket=t,
            template_text=setting.msg_template_ready if setting else "",
            shop_name=setting.shop_name if setting else "Mobile Repair Shop",
        )
        enriched.append({
            "ticket": t,
            "waiting_days": waiting_days,
            "balance_due": balance_due,
            "whatsapp_url": wa_url,
        })

    enriched.sort(key=lambda x: x["waiting_days"], reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="queue/ready.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "items": enriched,
        },
    )
