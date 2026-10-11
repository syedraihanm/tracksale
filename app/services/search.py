
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.ticket import Ticket


def escape_like(query_str: str) -> str:
    """Escape SQL LIKE special characters (% and _ and \\)."""
    return query_str.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_tickets(db: Session, query: str, limit: int = 20) -> list[Ticket]:
    """Search active (non-deleted) tickets matching query across ticket_no, customer name, phone, IMEI, model, brand."""
    q = query.strip()
    if not q or len(q) < 2:
        return []

    pattern = f"%{escape_like(q)}%"

    results = (
        db.query(Ticket)
        .join(Customer, Ticket.customer_id == Customer.id)
        .options(joinedload(Ticket.customer), joinedload(Ticket.items), joinedload(Ticket.payments))
        .filter(
            Ticket.is_deleted.is_(False),
            or_(
                Ticket.ticket_no.ilike(pattern),
                Customer.name.ilike(pattern),
                Customer.phone.ilike(pattern),
                Ticket.imei_or_serial.ilike(pattern),
                Ticket.device_brand.ilike(pattern),
                Ticket.device_model.ilike(pattern),
            ),
        )
        .order_by(Ticket.received_at.desc())
        .limit(limit)
        .all()
    )

    return results
