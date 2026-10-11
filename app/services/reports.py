from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.cash_closing import CashClosing
from app.models.enums import Outcome, PaymentMode, TicketStatus
from app.models.payment import Payment
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.timeutil import business_date, ist_date_range_to_utc_bounds


def compute_reports(
    db: Session,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """Compute complete analytics metrics for the given IST date range."""
    start_utc, end_utc = ist_date_range_to_utc_bounds(from_date, to_date)

    # 1. Payments in period (Gross revenue & Payment modes & Daily trend)
    period_payments = (
        db.query(Payment)
        .filter(
            Payment.is_deleted.is_(False),
            Payment.paid_at >= start_utc,
            Payment.paid_at <= end_utc,
        )
        .all()
    )

    gross_revenue = sum(p.amount for p in period_payments)

    mode_totals = {PaymentMode.CASH.value: 0, PaymentMode.CARD.value: 0, PaymentMode.UPI.value: 0}
    for p in period_payments:
        if p.mode in mode_totals:
            mode_totals[p.mode] += p.amount

    mode_percentages = {}
    for m, amt in mode_totals.items():
        if gross_revenue > 0:
            mode_percentages[m] = round((amt / gross_revenue) * 100, 1)
        else:
            mode_percentages[m] = 0.0

    # Daily revenue trend (zero-filled)
    daily_revenue_map = defaultdict(int)
    for p in period_payments:
        pay_ist_date = business_date(p.paid_at)
        daily_revenue_map[pay_ist_date] += p.amount

    daily_trend = []
    cur_d = from_date
    while cur_d <= to_date:
        daily_trend.append({
            "date": cur_d.strftime("%d-%b"),
            "full_date": cur_d.isoformat(),
            "amount": daily_revenue_map[cur_d],
        })
        cur_d += timedelta(days=1)

    # 2. Tickets delivered in period
    delivered_tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.items),
            joinedload(Ticket.child_tickets),
        )
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.delivered_at >= start_utc,
            Ticket.delivered_at <= end_utc,
        )
        .all()
    )

    billed_value = 0
    parts_cost = 0
    repaired_tickets: list[Ticket] = []
    part_purchases = defaultdict(lambda: {"count": 0, "total_cost": 0})

    for t in delivered_tickets:
        ticket_items = [i for i in t.items if not i.is_deleted]
        billed_value += sum(i.price_charged for i in ticket_items)
        part_items = [i for i in ticket_items if i.type == "part"]
        parts_cost += sum(i.cost_price for i in part_items)

        for p in part_items:
            key = p.description.strip().lower()
            orig_name = p.description.strip()
            part_purchases[key]["description"] = orig_name
            part_purchases[key]["count"] += 1
            part_purchases[key]["total_cost"] += p.cost_price

        if t.outcome == Outcome.REPAIRED.value:
            repaired_tickets.append(t)

    gross_margin_rupees = billed_value - parts_cost
    gross_margin_pct = round((gross_margin_rupees / billed_value) * 100, 1) if billed_value > 0 else 0.0

    devices_serviced = len(repaired_tickets)

    # 3. Avg Turnaround (tickets with ready_at in period)
    ready_in_period_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.ready_at.is_not(None),
            Ticket.ready_at >= start_utc,
            Ticket.ready_at <= end_utc,
        )
        .all()
    )

    if ready_in_period_tickets:
        turnaround_hours = [
            (t.ready_at - t.received_at).total_seconds() / 3600.0
            for t in ready_in_period_tickets
            if t.ready_at and t.received_at
        ]
        avg_turnaround_hours = round(sum(turnaround_hours) / len(turnaround_hours), 1) if turnaround_hours else 0.0
    else:
        avg_turnaround_hours = 0.0

    # 4. Avg Pickup Delay (repaired tickets delivered in period)
    pickup_delays = []
    for t in repaired_tickets:
        if t.delivered_at and t.ready_at:
            delay_h = (t.delivered_at - t.ready_at).total_seconds() / 3600.0
            pickup_delays.append(delay_h)

    avg_pickup_delay_hours = round(sum(pickup_delays) / len(pickup_delays), 1) if pickup_delays else 0.0

    # 5. Fix Success Rate
    # Repaired tickets delivered in period without a warranty return / all repaired tickets delivered in period
    repaired_without_warranty_return = 0
    for t in repaired_tickets:
        has_warranty_return = False
        if t.warranty_until:
            for child in t.child_tickets:
                if not child.is_deleted:
                    child_received_date = business_date(child.received_at)
                    if child_received_date <= t.warranty_until:
                        has_warranty_return = True
                        break
        if not has_warranty_return:
            repaired_without_warranty_return += 1

    if devices_serviced > 0:
        fix_success_rate = round((repaired_without_warranty_return / devices_serviced) * 100, 1)
    else:
        fix_success_rate = 0.0

    # Status transitions entering declined / unrepairable in period
    declined_count = (
        db.query(StatusHistory)
        .join(Ticket, StatusHistory.ticket_id == Ticket.id)
        .filter(
            Ticket.is_deleted.is_(False),
            StatusHistory.to_status == TicketStatus.DECLINED.value,
            StatusHistory.changed_at >= start_utc,
            StatusHistory.changed_at <= end_utc,
        )
        .count()
    )

    unrepairable_count = (
        db.query(StatusHistory)
        .join(Ticket, StatusHistory.ticket_id == Ticket.id)
        .filter(
            Ticket.is_deleted.is_(False),
            StatusHistory.to_status == TicketStatus.UNREPAIRABLE.value,
            StatusHistory.changed_at >= start_utc,
            StatusHistory.changed_at <= end_utc,
        )
        .count()
    )

    # 6. Demand: tickets received in period (Top brands, models, issue categories)
    received_tickets = (
        db.query(Ticket)
        .filter(
            Ticket.is_deleted.is_(False),
            Ticket.received_at >= start_utc,
            Ticket.received_at <= end_utc,
        )
        .all()
    )

    brand_counts = defaultdict(int)
    model_counts = defaultdict(int)
    issue_counts = defaultdict(int)

    for t in received_tickets:
        brand_counts[t.device_brand] += 1
        model_counts[t.device_model] += 1
        issue_counts[t.issue_category] += 1

    top_brands = sorted(brand_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # Most-bought parts: sorted by count desc, then cost desc
    most_bought_parts = sorted(
        part_purchases.values(),
        key=lambda x: (x["count"], x["total_cost"]),
        reverse=True,
    )

    # 7. Cash Variance History
    cash_closings = (
        db.query(CashClosing)
        .filter(
            CashClosing.date >= from_date,
            CashClosing.date <= to_date,
        )
        .order_by(CashClosing.date.asc())
        .all()
    )

    variance_history = [
        {
            "date": c.date.strftime("%d-%b-%Y"),
            "raw_date": c.date.isoformat(),
            "opening": c.opening_cash,
            "expected": c.expected_cash,
            "counted": c.counted_cash,
            "variance": c.variance,
            "note": c.note,
        }
        for c in cash_closings
    ]

    return {
        "from_date": from_date,
        "to_date": to_date,
        "gross_revenue": gross_revenue,
        "billed_value": billed_value,
        "parts_cost": parts_cost,
        "gross_margin_rupees": gross_margin_rupees,
        "gross_margin_pct": gross_margin_pct,
        "mode_totals": mode_totals,
        "mode_percentages": mode_percentages,
        "devices_serviced": devices_serviced,
        "avg_turnaround_hours": avg_turnaround_hours,
        "avg_pickup_delay_hours": avg_pickup_delay_hours,
        "fix_success_rate": fix_success_rate,
        "repaired_without_warranty_return": repaired_without_warranty_return,
        "declined_count": declined_count,
        "unrepairable_count": unrepairable_count,
        "top_brands": top_brands,
        "top_models": top_models,
        "top_issues": top_issues,
        "most_bought_parts": most_bought_parts,
        "daily_trend": daily_trend,
        "variance_history": variance_history,
    }


def compute_comparison_pct(curr: float, prev: float) -> str:
    """Compute % change between current and previous period value. Shows 'n/a' if prev is 0."""
    if prev == 0:
        return "n/a"
    change = ((curr - prev) / abs(prev)) * 100.0
    prefix = "+" if change > 0 else ""
    return f"{prefix}{round(change, 1)}%"


def get_previous_period_bounds(from_date: date, to_date: date) -> tuple[date, date]:
    """Calculate the immediately preceding window of equal length (A-21)."""
    length = (to_date - from_date).days + 1
    prev_to = from_date - timedelta(days=1)
    prev_from = prev_to - timedelta(days=length - 1)
    return prev_from, prev_to
