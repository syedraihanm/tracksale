from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket",
        back_populates="customer",
        cascade="none",
    )
