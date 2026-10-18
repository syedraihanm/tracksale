from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem
    from app.models.supplier import Supplier
    from app.models.ticket import Ticket


class TicketItem(Base, TimestampMixin):
    __tablename__ = "ticket_items"
    __table_args__ = (
        CheckConstraint(
            "type = 'part' OR (cost_price = 0 AND supplier_name IS NULL)",
            name="ck_ticket_items_labor_cost_supplier",
        ),
        CheckConstraint("price_charged >= 0", name="ck_ticket_items_price_charged"),
        CheckConstraint("cost_price >= 0", name="ck_ticket_items_cost_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'labor' or 'part'
    description: Mapped[str] = mapped_column(String(120), nullable=False)
    price_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supplier_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="items")
    inventory_item: Mapped["InventoryItem | None"] = relationship("InventoryItem", back_populates="ticket_items")
    supplier: Mapped["Supplier | None"] = relationship("Supplier", back_populates="ticket_items")
