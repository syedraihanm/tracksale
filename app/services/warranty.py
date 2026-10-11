from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.enums import TicketStatus
from app.models.ticket import Ticket
from app.services.errors import ValidationFailed
from app.services.tickets import create_ticket
from app.timeutil import business_date, utc_now


def is_under_warranty(ticket: Ticket, check_date: date | None = None, now: datetime | None = None) -> bool:
    """Check if ticket device is under warranty on given IST date (inclusive)."""
    if not ticket.warranty_until:
        return False
    current_date = check_date or business_date(now or utc_now())
    return ticket.warranty_until >= current_date


def create_warranty_return(
    db: Session,
    parent_ticket: Ticket,
    reported_issue: str,
    issue_category: str = "Other",
    technician_note: str | None = None,
    now: datetime | None = None,
) -> Ticket:
    """Create a new linked warranty return ticket for a delivered ticket."""
    if parent_ticket.status != TicketStatus.DELIVERED.value:
        raise ValidationFailed("Cannot create warranty return for non-delivered ticket")

    return create_ticket(
        db=db,
        customer_phone=parent_ticket.customer.phone,
        customer_name=parent_ticket.customer.name,
        device_brand=parent_ticket.device_brand,
        device_model=parent_ticket.device_model,
        reported_issue=reported_issue,
        issue_category=issue_category,
        imei_or_serial=parent_ticket.imei_or_serial,
        color=parent_ticket.color,
        parent_ticket_id=parent_ticket.id,
        now=now,
    )
