from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin
from app.timeutil import utc_now

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class StatusHistory(Base, TimestampMixin):
    __tablename__ = "status_history"
    __table_args__ = (
        Index("ix_status_history_ticket_id", "ticket_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="status_histories")
