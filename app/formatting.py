import re
from datetime import date, datetime

from app.timeutil import business_date, to_ist, utc_now


def format_inr(n: int | None, prefix: bool = True) -> str:
    """Format integer rupees with Indian number grouping (e.g. 1,25,000).

    Negatives formatted as -₹5,000 (or -5,000 if prefix=False).
    """
    if n is None:
        return "₹0" if prefix else "0"

    sign = "-" if n < 0 else ""
    abs_n = abs(int(n))
    s_abs = str(abs_n)

    if len(s_abs) <= 3:
        formatted = s_abs
    else:
        last3 = s_abs[-3:]
        rest = s_abs[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        formatted = ",".join(groups) + "," + last3

    if prefix:
        return f"{sign}₹{formatted}"
    return f"{sign}{formatted}"


def format_date(d: date | datetime | None) -> str:
    """Format as DD-MMM-YYYY (e.g. 09-Oct-2026)."""
    if d is None:
        return "-"
    if isinstance(d, datetime):
        d = to_ist(d).date()
    return d.strftime("%d-%b-%Y")


def format_time(dt: datetime | None) -> str:
    """Format as 12-hour time with AM/PM (e.g. 03:45 PM)."""
    if dt is None:
        return "-"
    dt_ist = to_ist(dt)
    return dt_ist.strftime("%I:%M %p")


def format_datetime(dt: datetime | None) -> str:
    """Format as DD-MMM-YYYY 12-hour time (e.g. 09-Oct-2026 03:45 PM)."""
    if dt is None:
        return "-"
    dt_ist = to_ist(dt)
    return dt_ist.strftime("%d-%b-%Y %I:%M %p")


def days_ago(dt: datetime | date | None, now_dt: datetime | None = None) -> int:
    """Return whole calendar days in IST since the given datetime or date."""
    if dt is None:
        return 0
    if isinstance(dt, datetime):
        dt_date = to_ist(dt).date()
    else:
        dt_date = dt
    current_date = business_date(now_dt or utc_now())
    return max(0, (current_date - dt_date).days)


def normalize_phone(raw: str) -> str:
    """Normalize phone number by stripping spaces, dashes, +91, and leading 0.

    Must result in exactly 10 digits.
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", raw.strip())
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    if not (len(cleaned) == 10 and cleaned.isdigit()):
        raise ValueError("Phone number must be exactly 10 digits")
    return cleaned


def parse_money(raw: str | int | None) -> int:
    """Parse user money input to whole integer rupees.

    Strips commas, spaces, ₹ symbol. Rejects decimals.
    """
    if raw is None or raw == "":
        return 0
    if isinstance(raw, int):
        return raw

    s = str(raw).strip().replace("₹", "").replace(",", "").replace(" ", "")
    if "." in s:
        raise ValueError("Enter whole rupees only (no decimals)")
    if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
        raise ValueError("Invalid amount")
    return int(s)
