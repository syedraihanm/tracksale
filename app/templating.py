from fastapi.templating import Jinja2Templates
from sqlalchemy import func

from app.formatting import (
    days_ago,
    format_date,
    format_datetime,
    format_inr,
    format_time,
)
from app.models.enums import issue_category_label

def shell_navigation_counts(request):
    db = getattr(request.state, "template_db_session", None)
    if db is None or request.headers.get("HX-Request") == "true":
        return {"nav_active_ticket_count": 0, "nav_ready_ticket_count": 0}

    try:
        from app.models.enums import TicketStatus
        from app.models.ticket import Ticket

        counts = (
            db.query(Ticket.status, func.count(Ticket.id))
            .filter(Ticket.is_deleted.is_(False))
            .group_by(Ticket.status)
            .all()
        )
        status_counts = dict(counts)
        active_statuses = (
            TicketStatus.RECEIVED.value,
            TicketStatus.AWAITING_APPROVAL.value,
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.AWAITING_PARTS.value,
            TicketStatus.READY_FOR_PICKUP.value,
        )
        return {
            "nav_active_ticket_count": sum(status_counts.get(status, 0) for status in active_statuses),
            "nav_ready_ticket_count": status_counts.get(TicketStatus.READY_FOR_PICKUP.value, 0),
        }
    except Exception:
        return {"nav_active_ticket_count": 0, "nav_ready_ticket_count": 0}


templates = Jinja2Templates(directory="app/templates", context_processors=[shell_navigation_counts])

# Register custom Jinja filters on the shared environment
templates.env.filters["inr"] = format_inr
templates.env.filters["date_ist"] = format_date
templates.env.filters["time_ist"] = format_time
templates.env.filters["datetime_ist"] = format_datetime
templates.env.filters["ist_datetime"] = format_datetime
templates.env.filters["ist_date"] = format_date
templates.env.filters["days_ago"] = days_ago
templates.env.filters["issue_category_label"] = issue_category_label
