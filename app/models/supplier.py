from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin
from app.timeutil import utc_now

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem
    from app.models.ticket_item import TicketItem


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    ticket_items: Mapped[list["TicketItem"]] = relationship("TicketItem", back_populates="supplier")
    inventory_items: Mapped[list["InventoryItem"]] = relationship("InventoryItem", back_populates="supplier")
    payments: Mapped[list["SupplierPayment"]] = relationship(
        "SupplierPayment",
        back_populates="supplier",
        order_by="desc(SupplierPayment.paid_at)",
    )


class SupplierPayment(Base, TimestampMixin):
    __tablename__ = "supplier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_supplier_payments_amount_pos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="cash")  # cash, upi, bank_transfer, card, cheque
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)  # UTR, transaction ref, cheque no
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, nullable=False, index=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="payments")
