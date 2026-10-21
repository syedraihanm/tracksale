from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.ticket import Ticket
from app.services.audit import record_audit
from app.services.payments import get_ticket_totals
from app.services.warranty import is_under_warranty
from app.timeutil import utc_now


def get_customer_summary(db: Session, customer_id: int) -> dict[str, Any] | None:
    """Retrieve customer details, their non-deleted tickets, total spent, and warranty statuses."""
    customer = (
        db.query(Customer)
        .options(
            joinedload(Customer.tickets).joinedload(Ticket.payments),
            joinedload(Customer.tickets).joinedload(Ticket.items),
        )
        .filter(Customer.id == customer_id)
        .first()
    )
    if not customer:
        return None

    non_deleted_tickets = [t for t in customer.tickets if not t.is_deleted]
    # Sort newest received first
    non_deleted_tickets.sort(key=lambda t: t.received_at, reverse=True)

    total_spent = 0
    ticket_cards = []
    for t in non_deleted_tickets:
        customer_total, net_paid, balance_due = get_ticket_totals(t)
        total_spent += net_paid
        under_warranty = is_under_warranty(t)
        ticket_cards.append({
            "ticket": t,
            "items_total": customer_total,
            "customer_total": customer_total,
            "customer_total_set": customer_total > 0,
            "net_paid": net_paid,
            "balance_due": balance_due,
            "under_warranty": under_warranty,
        })

    return {
        "customer": customer,
        "tickets": ticket_cards,
        "total_spent": total_spent,
    }


def update_customer_notes(
    db: Session,
    customer: Customer,
    notes: str | None,
    now: datetime | None = None,
) -> Customer:
    """Update customer notes with audit."""
    current_time = now or utc_now()
    new_notes = notes.strip() if notes else None
    if customer.notes != new_notes:
        old_notes = customer.notes
        customer.notes = new_notes
        customer.updated_at = current_time
        record_audit(
            db=db,
            entity="customer",
            entity_id=customer.id,
            action="update",
            changed_fields={"notes": {"old": old_notes, "new": new_notes}},
            reason="Customer notes updated",
            now=current_time,
        )
    return customer
