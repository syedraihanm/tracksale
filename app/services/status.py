from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.enums import Outcome, TicketStatus
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.services.audit import record_audit
from app.services.errors import InvalidTransition, NeedsConfirmation
from app.timeutil import business_date, utc_now

VALID_TRANSITIONS: dict[str, list[str]] = {
    TicketStatus.RECEIVED.value: [
        TicketStatus.AWAITING_APPROVAL.value,
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.DECLINED.value,
        TicketStatus.UNREPAIRABLE.value,
    ],
    TicketStatus.AWAITING_APPROVAL.value: [
        TicketStatus.IN_PROGRESS.value,
        TicketStatus.DECLINED.value,
    ],
    TicketStatus.IN_PROGRESS.value: [
        TicketStatus.AWAITING_PARTS.value,
        TicketStatus.READY_FOR_PICKUP.value,
        TicketStatus.UNREPAIRABLE.value,
    ],
    TicketStatus.AWAITING_PARTS.value: [
        TicketStatus.IN_PROGRESS.value,
    ],
    TicketStatus.READY_FOR_PICKUP.value: [
        TicketStatus.DELIVERED.value,
        TicketStatus.IN_PROGRESS.value,
    ],
    TicketStatus.DECLINED.value: [
        TicketStatus.DELIVERED.value,
    ],
    TicketStatus.UNREPAIRABLE.value: [
        TicketStatus.DELIVERED.value,
    ],
    TicketStatus.DELIVERED.value: [],
}


def can_transition(from_status: str, to_status: str) -> bool:
    """Check if the transition between two statuses is permitted."""
    allowed = VALID_TRANSITIONS.get(from_status, [])
    return to_status in allowed


def get_allowed_transitions(current_status: str) -> list[str]:
    """Return list of allowed next status values."""
    return VALID_TRANSITIONS.get(current_status, [])


def transition_ticket(
    db: Session,
    ticket: Ticket,
    to_status: str,
    note: str | None = None,
    confirm_pending_balance: bool = False,
    clear_passcode: bool = False,
    now: datetime | None = None,
) -> Ticket:
    """Transition a ticket to a new status with validation, history, and audit logging."""
    current_time = now or utc_now()
    old_status = ticket.status

    if not can_transition(old_status, to_status):
        raise InvalidTransition(f"Cannot transition ticket from '{old_status}' to '{to_status}'")

    # Delivery gate checks
    if to_status == TicketStatus.DELIVERED.value:
        # Calculate balance
        items_total = sum(i.price_charged for i in ticket.items if not i.is_deleted)
        net_paid = sum(p.amount for p in ticket.payments if not p.is_deleted)
        balance_due = items_total - net_paid

        from app.formatting import format_inr
        if balance_due != 0 and not confirm_pending_balance:
            if balance_due > 0:
                raise NeedsConfirmation(f"Ticket has an unpaid balance of {format_inr(balance_due)}. Confirm delivery with pending balance?")
            else:
                raise NeedsConfirmation(f"Ticket has a credit balance of {format_inr(abs(balance_due))}. Suggest refund or confirm delivery?")

        # Set delivery timestamps and outcome
        ticket.delivered_at = current_time
        if old_status == TicketStatus.READY_FOR_PICKUP.value:
            ticket.outcome = Outcome.REPAIRED.value
        elif old_status == TicketStatus.DECLINED.value:
            ticket.outcome = Outcome.DECLINED.value
        elif old_status == TicketStatus.UNREPAIRABLE.value:
            ticket.outcome = Outcome.UNREPAIRABLE.value

        # Warranty computation
        if ticket.outcome == Outcome.REPAIRED.value and ticket.warranty_days > 0:
            delivery_ist_date = business_date(current_time)
            ticket.warranty_until = delivery_ist_date + timedelta(days=ticket.warranty_days)
        else:
            ticket.warranty_until = None

        if clear_passcode:
            ticket.passcode_encrypted = None

        if balance_due != 0 and confirm_pending_balance:
            record_audit(
                db=db,
                entity="ticket",
                entity_id=ticket.id,
                ticket_id=ticket.id,
                action="update",
                changed_fields={"delivered_with_balance": {"old": None, "new": balance_due}},
                reason="delivered with pending balance",
                now=current_time,
            )

    elif to_status == TicketStatus.READY_FOR_PICKUP.value:
        ticket.ready_at = current_time

    ticket.status = to_status
    ticket.updated_at = current_time

    # Record status history
    history = StatusHistory(
        ticket_id=ticket.id,
        from_status=old_status,
        to_status=to_status,
        changed_at=current_time,
        note=note.strip() if note else None,
    )
    db.add(history)

    # Audit transition
    record_audit(
        db=db,
        entity="ticket",
        entity_id=ticket.id,
        ticket_id=ticket.id,
        action="update",
        changed_fields={"status": {"old": old_status, "new": to_status}},
        reason=note.strip() if note else None,
        now=current_time,
    )

    return ticket
