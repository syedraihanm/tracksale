from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login
from app.models.audit_log import AuditLog
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.templating import templates
from app.timeutil import ist_day_to_utc_bounds

router = APIRouter(prefix="/audit", dependencies=[Depends(require_login)])


@router.get("", response_class=HTMLResponse)
def audit_log_view(
    request: Request,
    entity: str | None = Query(None),
    ticket_no: str | None = Query(None),
    date_str: str | None = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    query = db.query(AuditLog)

    if entity and entity.strip():
        query = query.filter(AuditLog.entity == entity.strip())

    if ticket_no and ticket_no.strip():
        # Look up ticket id by ticket_no
        t = db.query(Ticket).filter(Ticket.ticket_no.ilike(f"%{ticket_no.strip()}%")).first()
        if t:
            query = query.filter(AuditLog.ticket_id == t.id)
        else:
            query = query.filter(AuditLog.id == -1)  # No match

    if date_str and date_str.strip():
        try:
            d = date.fromisoformat(date_str.strip())
            start_utc, end_utc = ist_day_to_utc_bounds(d)
            query = query.filter(AuditLog.timestamp >= start_utc, AuditLog.timestamp <= end_utc)
        except ValueError:
            pass

    logs = query.order_by(desc(AuditLog.timestamp)).limit(100).all()

    # Preload ticket numbers for display
    ticket_ids = {l.ticket_id for l in logs if l.ticket_id}
    ticket_map = {}
    if ticket_ids:
        tickets = db.query(Ticket.id, Ticket.ticket_no).filter(Ticket.id.in_(ticket_ids)).all()
        ticket_map = {t[0]: t[1] for t in tickets}

    return templates.TemplateResponse(
        request=request,
        name="audit/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "logs": logs,
            "ticket_map": ticket_map,
            "selected_entity": entity,
            "selected_ticket_no": ticket_no,
            "selected_date": date_str,
        },
    )
