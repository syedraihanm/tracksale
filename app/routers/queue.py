from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.deps import get_current_session, require_login
from app.formatting import days_ago
from app.models.enums import TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.services.payments import get_ticket_totals
from app.services.receipts import generate_whatsapp_url
from app.services.status import get_allowed_transitions
from app.templating import templates
from app.timeutil import utc_now

router = APIRouter(dependencies=[Depends(require_login)])

ACTIVE_STATUSES = [
    TicketStatus.RECEIVED.value,
    TicketStatus.AWAITING_APPROVAL.value,
    TicketStatus.IN_PROGRESS.value,
    TicketStatus.AWAITING_PARTS.value,
    TicketStatus.READY_FOR_PICKUP.value,
]

CLOSED_STATUSES = [
    TicketStatus.DELIVERED.value,
    TicketStatus.DECLINED.value,
    TicketStatus.UNREPAIRABLE.value,
]

STATUS_ORDER = ACTIVE_STATUSES + [
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
    TicketStatus.DELIVERED.value: "Delivered (Last 30 Days)",
    TicketStatus.DECLINED.value: "Declined",
    TicketStatus.UNREPAIRABLE.value: "Unrepairable",
}


@router.get("/", response_class=HTMLResponse)
@router.get("/queue", response_class=HTMLResponse, include_in_schema=False)
def queue_view(
    request: Request,
    status: list[str] = Query(default=[]),
    queue_focus: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Grouped table ticket queue view."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    now = utc_now()
    thirty_days_ago = now - timedelta(days=30)

    # Compute live counts for all statuses
    counts_query = (
        db.query(Ticket.status, func.count(Ticket.id))
        .filter(Ticket.is_deleted.is_(False))
        .group_by(Ticket.status)
        .all()
    )
    total_ticket_count = sum(count for _, count in counts_query)
    status_counts = {s: 0 for s in STATUS_ORDER}
    for st, cnt in counts_query:
        if st in status_counts:
            status_counts[st] = cnt

    # Restrict delivered count to last 30 days
    delivered_count = (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.status == TicketStatus.DELIVERED.value,
            or_(
                Ticket.delivered_at >= thirty_days_ago,
                Ticket.delivered_at.is_(None),
            ),
        )
        .scalar()
    ) or 0
    status_counts[TicketStatus.DELIVERED.value] = delivered_count
    all_active_count = sum(status_counts.get(s, 0) for s in ACTIVE_STATUSES)
    queue_focus = queue_focus if queue_focus == "balance_due" else ""

    # Today's strip uses the same active queue data and shop timezone as the rest of the app.
    active_tickets = (
        db.query(Ticket)
        .options(
            selectinload(Ticket.items),
            selectinload(Ticket.payments),
            selectinload(Ticket.status_histories),
        )
        .filter(Ticket.is_deleted.is_(False), Ticket.status.in_(ACTIVE_STATUSES))
        .all()
    )
    ready_tickets = [ticket for ticket in active_tickets if ticket.status == TicketStatus.READY_FOR_PICKUP.value]
    ready_oldest_days = max(
        (
            days_ago(
                max(
                    (history.changed_at for history in ticket.status_histories if history.to_status == ticket.status),
                    default=ticket.ready_at or ticket.received_at,
                ),
                now_dt=now,
            )
            for ticket in ready_tickets
        ),
        default=0,
    )
    balance_to_collect = 0
    for ticket in active_tickets:
        items_total = sum(item.price_charged for item in ticket.items if not item.is_deleted)
        net_paid = sum(payment.amount for payment in ticket.payments if not payment.is_deleted)
        balance_to_collect += max(items_total - net_paid, 0)

    # Check whether the request has explicit filter parameters
    is_filtering = "status" in request.query_params or "filtered" in request.query_params
    if is_filtering:
        selected_statuses = [s for s in status if s in STATUS_ORDER]
        is_all_active = not queue_focus and set(selected_statuses) == set(ACTIVE_STATUSES)
    else:
        selected_statuses = ACTIVE_STATUSES.copy()
        is_all_active = not queue_focus

    is_filtered_custom = not is_all_active

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

    # Group tickets by status order and build flat enriched list
    grouped: dict[str, list[dict]] = {s: [] for s in STATUS_ORDER if s in selected_statuses}
    all_tickets_list: list[dict] = []

    for t in tickets:
        if t.status not in grouped:
            continue
        items_total, net_paid, balance_due = get_ticket_totals(t)
        if queue_focus == "balance_due" and balance_due <= 0:
            continue
        age_days = days_ago(t.received_at, now_dt=now)

        # In status days from latest status history
        histories = [h for h in t.status_histories if h.to_status == t.status]
        latest_hist = max(histories, key=lambda h: h.changed_at) if histories else None
        in_status_days = days_ago(latest_hist.changed_at if latest_hist else t.received_at, now_dt=now)

        # Warning badges
        is_ready_stale_7d = in_status_days > 7 and t.status == TicketStatus.READY_FOR_PICKUP.value
        is_approval_stale_2d = in_status_days > 2 and t.status == TicketStatus.AWAITING_APPROVAL.value

        # Urgency scoring for default sorting
        if is_ready_stale_7d:
            urgency_score = (0, -in_status_days)
        elif is_approval_stale_2d:
            urgency_score = (1, -in_status_days)
        elif t.status == TicketStatus.READY_FOR_PICKUP.value:
            urgency_score = (2, -in_status_days)
        elif t.status == TicketStatus.AWAITING_APPROVAL.value:
            urgency_score = (3, -in_status_days)
        elif t.status == TicketStatus.IN_PROGRESS.value:
            urgency_score = (4, -age_days)
        elif t.status == TicketStatus.AWAITING_PARTS.value:
            urgency_score = (5, -in_status_days)
        elif t.status == TicketStatus.RECEIVED.value:
            urgency_score = (6, -age_days)
        elif t.status in (TicketStatus.DECLINED.value, TicketStatus.UNREPAIRABLE.value):
            urgency_score = (7, -in_status_days)
        else:
            urgency_score = (8, -age_days)

        item_data = {
            "ticket": t,
            "items_total": items_total,
            "net_paid": net_paid,
            "balance_due": balance_due,
            "age_days": age_days,
            "in_status_days": in_status_days,
            "is_stale_7d": in_status_days > 7 and t.status != TicketStatus.DELIVERED.value,
            "is_ready_stale_7d": is_ready_stale_7d,
            "is_approval_stale_2d": is_approval_stale_2d,
            "urgency_score": urgency_score,
            "allowed_transitions": get_allowed_transitions(t.status),
        }

        grouped[t.status].append(item_data)
        all_tickets_list.append(item_data)

    # Sort all_tickets by urgency by default
    all_tickets_list.sort(key=lambda x: x["urgency_score"])

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
        "all_tickets": all_tickets_list,
        "total_count": total_count,
        "total_ticket_count": total_ticket_count,
        "all_statuses": STATUS_ORDER,
        "active_statuses": ACTIVE_STATUSES,
        "closed_statuses": CLOSED_STATUSES,
        "status_display_names": STATUS_DISPLAY_NAMES,
        "selected_statuses": selected_statuses,
        "status_counts": status_counts,
        "all_active_count": all_active_count,
        "is_all_active": is_all_active,
        "is_filtered_custom": is_filtered_custom,
        "queue_focus": queue_focus,
        "today_metrics": {
            "in_progress": status_counts.get(TicketStatus.IN_PROGRESS.value, 0),
            "ready_for_pickup": len(ready_tickets),
            "ready_oldest_days": ready_oldest_days,
            "balance_to_collect": balance_to_collect,
        },
        "today_focus_in_progress": not queue_focus and selected_statuses == [TicketStatus.IN_PROGRESS.value],
        "today_focus_ready": not queue_focus and selected_statuses == [TicketStatus.READY_FOR_PICKUP.value],
        "today_focus_balance": queue_focus == "balance_due",
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
