from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin
from app.timeutil import utc_now


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_ticket_id", "ticket_id"),
        Index("ix_audit_log_entity_id", "entity", "entity_id"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 'create', 'update', 'delete'
    changed_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
