from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin
from app.timeutil import utc_now

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "amount <> 0 AND ((kind = 'refund' AND amount < 0) OR (kind <> 'refund' AND amount > 0))",
            name="ck_payments_amount_kind_sign",
        ),
        Index("ix_payments_ticket_id", "ticket_id"),
        Index("ix_payments_paid_at", "paid_at"),
        Index("ix_payments_mode_paid_at", "mode", "paid_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # 'cash', 'card', 'upi'
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # 'advance', 'final', 'refund'
    paid_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="payments")
