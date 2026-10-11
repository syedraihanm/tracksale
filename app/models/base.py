from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db import UTCDateTime
from app.timeutil import utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
