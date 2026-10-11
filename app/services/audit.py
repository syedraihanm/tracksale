from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.timeutil import utc_now


def record_audit(
    db: Session,
    entity: str,
    entity_id: int,
    action: str,
    changed_fields: dict[str, Any] | None = None,
    reason: str | None = None,
    ticket_id: int | None = None,
    now: datetime | None = None,
) -> AuditLog:
    """Record an append-only audit log entry."""
    entry = AuditLog(
        entity=entity,
        entity_id=entity_id,
        ticket_id=ticket_id,
        action=action,
        changed_fields=changed_fields,
        reason=reason,
        timestamp=now or utc_now(),
    )
    db.add(entry)
    return entry
