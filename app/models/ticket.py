from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin
from app.timeutil import utc_now

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.payment import Payment
    from app.models.status_history import StatusHistory
    from app.models.ticket_item import TicketItem


class Ticket(Base, TimestampMixin):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    device_brand: Mapped[str] = mapped_column(String(60), nullable=False)
    device_model: Mapped[str] = mapped_column(String(60), nullable=False)
    imei_or_serial: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    color: Mapped[str | None] = mapped_column(String(30), nullable=True)
    passcode_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_issue: Mapped[str] = mapped_column(Text, nullable=False)
    issue_category: Mapped[str] = mapped_column(String(50), nullable=False, default="Other")
    intake_condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estimate_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="received", index=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    technician_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False, index=True)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)

    warranty_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    parent_ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="tickets")
    items: Mapped[list["TicketItem"]] = relationship("TicketItem", back_populates="ticket", cascade="none")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="ticket", cascade="none")
    status_histories: Mapped[list["StatusHistory"]] = relationship("StatusHistory", back_populates="ticket", cascade="none")
    parent_ticket: Mapped[Optional["Ticket"]] = relationship(
        "Ticket",
        remote_side="Ticket.id",
        foreign_keys=[parent_ticket_id],
        back_populates="child_tickets",
    )
    child_tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        foreign_keys=[parent_ticket_id],
        back_populates="parent_ticket",
    )
