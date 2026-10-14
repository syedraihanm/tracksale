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


def test_settings_secret_validation():
    from cryptography.fernet import Fernet
    from pydantic import ValidationError

    from app.config import Settings

    # Invalid Fernet key raises ValidationError/ValueError
    with pytest.raises(ValidationError):
        Settings(PASSCODE_ENCRYPTION_KEY="not-a-valid-fernet-key")

    valid_key = Fernet.generate_key().decode()

    # Production mode with default/weak secret raises ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="change-this-in-production-use-scripts-gen-key-py",
            PASSCODE_ENCRYPTION_KEY=valid_key,
        )

    # Production mode with short secret key raises ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="too-short",
            PASSCODE_ENCRYPTION_KEY=valid_key,
        )

    # Production mode with insecure default passcode encryption key raises ValidationError
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SECRET_KEY="a-very-strong-production-secret-key-32-chars-min",
            PASSCODE_ENCRYPTION_KEY="PH_13btabNyspTjWnDstwe9GTl3rMAEREI71jCXTQbA=",
        )

    # Valid production settings pass
    valid_settings = Settings(
        APP_ENV="production",
        SECRET_KEY="a-very-strong-production-secret-key-32-chars-min",
        PASSCODE_ENCRYPTION_KEY=valid_key,
    )
    assert valid_settings.is_production is True


def test_alembic_migrations_and_zero_drift(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect, text

    from alembic import command
    from app.db import Base

    db_file = tmp_path / "mig_test.db"
    db_url = f"sqlite:///{db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade head
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    expected_tables = {
        "settings",
        "customers",
        "tickets",
        "ticket_items",
        "payments",
        "status_history",
        "cash_closings",
        "audit_log",
        "inventory_items",
    }
    actual_tables = set(inspector.get_table_names())
    assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"

    # Verify ticket_items has inventory_item_id
    cols = {c["name"] for c in inspector.get_columns("ticket_items")}
    assert "inventory_item_id" in cols

    # Verify zero diff against Base.metadata
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        diff = compare_metadata(mc, Base.metadata)
        table_or_col_diffs = [
            d for d in diff if d[0] in ("add_table", "remove_table", "add_column", "remove_column")
        ]
        assert table_or_col_diffs == [], f"Schema drift detected: {diff}"

        # Verify anti-delete trigger on inventory_items
        conn.execute(
            text(
                "INSERT INTO inventory_items (id, spare_type, model, quantity, cost_price, selling_price, is_deleted, created_at, updated_at) "
                "VALUES (1, 'Screen', 'Pixel 7', 5, 2000, 3500, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.commit()

        with pytest.raises(Exception, match="Hard delete is forbidden on inventory_items"):
            conn.execute(text("DELETE FROM inventory_items WHERE id = 1"))
            conn.commit()
    engine.dispose()


