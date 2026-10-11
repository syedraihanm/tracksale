from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from app.formatting import (
    days_ago,
    format_date,
    format_datetime,
    format_inr,
    format_time,
    normalize_phone,
    parse_money,
)
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.ticket import Ticket
from app.timeutil import IST, ist_day_to_utc_bounds, utc_now


def test_format_inr_table():
    # Exact table from spec 14.2: 0, 999, 1000, 99999, 100000, 125000, 1234567, -5000
    assert format_inr(0) == "₹0"
    assert format_inr(999) == "₹999"
    assert format_inr(1000) == "₹1,000"
    assert format_inr(99999) == "₹99,999"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(125000) == "₹1,25,000"
    assert format_inr(1234567) == "₹12,34,567"
    assert format_inr(-5000) == "-₹5,000"
    # without prefix
    assert format_inr(125000, prefix=False) == "1,25,000"
    assert format_inr(-5000, prefix=False) == "-5,000"


def test_date_time_formats():
    # 09-Oct-2026 03:45 PM IST
    dt_ist = datetime(2026, 10, 9, 15, 45, tzinfo=IST)
    dt_utc = dt_ist.astimezone(UTC)

    assert format_date(dt_utc) == "09-Oct-2026"
    assert format_time(dt_utc) == "03:45 PM"
    assert format_datetime(dt_utc) == "09-Oct-2026 03:45 PM"


def test_days_ago():
    now_dt = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
    assert days_ago(t1, now_dt=now_dt) == 2
    assert days_ago(now_dt, now_dt=now_dt) == 0


def test_normalize_phone():
    assert normalize_phone("9876543210") == "9876543210"
    assert normalize_phone("+919876543210") == "9876543210"
    assert normalize_phone("+91 98765 43210") == "9876543210"
    assert normalize_phone("09876543210") == "9876543210"
    assert normalize_phone("919876543210") == "9876543210"
    assert normalize_phone(" (987) 654-3210 ") == "9876543210"

    with pytest.raises(ValueError):
        normalize_phone("12345")
    with pytest.raises(ValueError):
        normalize_phone("987654321012")
    with pytest.raises(ValueError):
        normalize_phone("abcdefghij")


def test_parse_money():
    assert parse_money("₹1,25,000") == 125000
    assert parse_money("  500  ") == 500
    assert parse_money(1000) == 1000
    assert parse_money("") == 0
    assert parse_money(None) == 0

    with pytest.raises(ValueError, match="whole rupees"):
        parse_money("500.50")


def test_timeutil_ist_bounds():
    d = date(2026, 10, 9)
    start_utc, end_utc = ist_day_to_utc_bounds(d)
    # Start of day in IST is 2026-10-09 00:00:00 IST -> 2026-10-08 18:30:00 UTC
    assert start_utc == datetime(2026, 10, 8, 18, 30, tzinfo=UTC)
    # End of day in IST is 2026-10-09 23:59:59.999999 IST -> 2026-10-09 18:29:59.999999 UTC
    assert end_utc.year == 2026
    assert end_utc.month == 10
    assert end_utc.day == 9
    assert end_utc.hour == 18
    assert end_utc.minute == 29


def test_triggers_prevent_hard_deletes(temp_db):
    # Insert customer and ticket
    c = Customer(name="Test Customer", phone="9876543210")
    temp_db.add(c)
    temp_db.commit()

    t = Ticket(
        ticket_no="R-1001",
        customer_id=c.id,
        device_brand="Samsung",
        device_model="M31",
        reported_issue="Screen broken",
        intake_condition={},
        status="received",
        received_at=utc_now(),
    )
    temp_db.add(t)
    temp_db.commit()

    # Attempt hard delete on tickets -> trigger must raise abort
    with pytest.raises(Exception, match="Hard delete is forbidden on tickets"):
        temp_db.execute(text("DELETE FROM tickets WHERE id = :id"), {"id": t.id})
        temp_db.commit()
    temp_db.rollback()

    # Audit log test
    audit = AuditLog(
        entity="ticket",
        entity_id=t.id,
        action="create",
        timestamp=utc_now(),
    )
    temp_db.add(audit)
    temp_db.commit()

    with pytest.raises(Exception, match="Update is forbidden on audit_log"):
        temp_db.execute(text("UPDATE audit_log SET action = 'update' WHERE id = :id"), {"id": audit.id})
        temp_db.commit()
    temp_db.rollback()

    with pytest.raises(Exception, match="Hard delete is forbidden on audit_log"):
        temp_db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": audit.id})
        temp_db.commit()
    temp_db.rollback()
