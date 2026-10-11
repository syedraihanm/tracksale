from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

# Self-check ZoneInfo load
try:
    IST = ZoneInfo("Asia/Kolkata")
except Exception as e:
    raise RuntimeError(f"Failed to load Asia/Kolkata timezone: {e}") from e


def utc_now() -> datetime:
    """Return the current time in UTC, timezone-aware."""
    return datetime.now(UTC)


def to_ist(dt: datetime) -> datetime:
    """Convert any timezone-aware datetime to IST."""
    if dt.tzinfo is None:
        # Fallback if a naive datetime was supplied (treat as UTC)
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)


def business_date(dt: datetime | None = None) -> date:
    """Return the calendar date in IST for a given datetime (or now)."""
    if dt is None:
        dt = utc_now()
    return to_ist(dt).date()


def ist_day_to_utc_bounds(d: date) -> tuple[datetime, datetime]:
    """Convert an IST calendar date to start and end UTC datetime bounds.

    Returns:
        (start_utc, end_utc) where start is inclusive (00:00:00 IST) and end is inclusive (23:59:59.999999 IST).
    """
    start_ist = datetime.combine(d, time.min, tzinfo=IST)
    end_ist = datetime.combine(d, time.max, tzinfo=IST)
    return start_ist.astimezone(UTC), end_ist.astimezone(UTC)


def ist_date_range_to_utc_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Convert an inclusive IST date range to UTC bounds."""
    start_ist = datetime.combine(start_date, time.min, tzinfo=IST)
    end_ist = datetime.combine(end_date, time.max, tzinfo=IST)
    return start_ist.astimezone(UTC), end_ist.astimezone(UTC)
