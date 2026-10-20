
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin

DEFAULT_RECEIPT_TERMS = (
    "1. Estimates may change after diagnosis and your approval will be sought. "
    "2. Repaired devices carry the warranty stated on this receipt for the repaired part/fault only; physical or water damage voids it. "
    "4. Please present this receipt or ticket number at pickup."
)

DEFAULT_MSG_INTAKE = (
    "Hi {name}, we received your {device}. Ticket {ticket_no}. Issue: {issue}. Thank you, {shop_name}."
)

DEFAULT_MSG_READY = (
    "Hi {name}, your {device} is ready for pickup. Ticket {ticket_no}. Amount due: ₹{due}. {shop_name}"
)


class Settings(Base, TimestampMixin):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_name: Mapped[str] = mapped_column(String(100), default="AMEE MOBILES", nullable=False)
    shop_phone: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    shop_address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    receipt_terms_text: Mapped[str] = mapped_column(Text, default=DEFAULT_RECEIPT_TERMS, nullable=False)
    default_warranty_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    owner_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ticket_no_prefix: Mapped[str] = mapped_column(String(10), default="R", nullable=False)
    next_ticket_seq: Mapped[int] = mapped_column(Integer, default=1001, nullable=False)
    msg_template_intake: Mapped[str] = mapped_column(Text, default=DEFAULT_MSG_INTAKE, nullable=False)
    msg_template_ready: Mapped[str] = mapped_column(Text, default=DEFAULT_MSG_READY, nullable=False)
    setup_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
