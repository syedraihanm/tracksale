from datetime import date, datetime

from sqlalchemy import Boolean, Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.base import TimestampMixin


class CashClosing(Base, TimestampMixin):
    __tablename__ = "cash_closings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    opening_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counted_cash: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    variance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reopened_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
