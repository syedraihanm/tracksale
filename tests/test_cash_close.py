from datetime import UTC, datetime

import pytest

from app.models.enums import PaymentKind
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret
from app.services.cash_close import (
    close_cash_day,
    compute_day_cash_summary,
    reopen_cash_day,
)
from app.services.errors import PinRequired, ValidationFailed
from app.services.payments import add_payment
from app.services.tickets import create_ticket
from app.timeutil import IST, business_date


def test_cash_calculation_and_variance(temp_db):
    """Test expected cash computation and variance calculation."""
    # Set owner PIN
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    day_t = business_date()

    # Day T starts with opening cash = 2000
    # Customer 1 pays ₹1000 cash
    t1 = create_ticket(
        db=temp_db,
        customer_phone="9820011111",
        customer_name="Cash User 1",
        device_brand="Brand",
        device_model="Model",
        reported_issue="Issue",
    )
    add_payment(temp_db, t1, amount=1000, mode="cash", kind=PaymentKind.FINAL.value)

    # Customer 2 pays ₹1500 UPI (should NOT affect cash)
    t2 = create_ticket(
        db=temp_db,
        customer_phone="9820022222",
        customer_name="UPI User",
        device_brand="Brand",
        device_model="Model",
        reported_issue="Issue",
    )
    add_payment(temp_db, t2, amount=1500, mode="upi", kind=PaymentKind.FINAL.value)

    # Customer 1 gets ₹200 cash refund
    add_payment(temp_db, t1, amount=200, mode="cash", kind=PaymentKind.REFUND.value, note="Minor delay refund")
    temp_db.commit()

    summary = compute_day_cash_summary(temp_db, day_t, opening_cash=2000)
    # Expected: 2000 + 1000 - 200 = 2800
    assert summary["cash_net"] == 800
    assert summary["upi_net"] == 1500
    assert summary["expected_cash"] == 2800

    # Counted cash is 2750 (variance = -50)
    closing = close_cash_day(
        db=temp_db,
        target_date=day_t,
        opening_cash=2000,
        counted_cash=2750,
        note="Short ₹50 for tea",
    )
    temp_db.commit()

    assert closing.is_closed is True
    assert closing.counted_cash == 2750
    assert closing.expected_cash == 2800
    assert closing.variance == -50


def test_reopen_cash_day_with_pin(temp_db):
    """AC6: Reopening a closed day requires Owner PIN and non-empty reason, and is audited."""
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    day_t = business_date()
    close_cash_day(temp_db, day_t, opening_cash=0, counted_cash=3000)
    temp_db.commit()

    # Reopen without valid PIN
    with pytest.raises(PinRequired):
        reopen_cash_day(temp_db, day_t, owner_pin="wrong", reason="Forgot evening repair")

    # Reopen without reason
    with pytest.raises(ValidationFailed):
        reopen_cash_day(temp_db, day_t, owner_pin="1234", reason="")

    # Reopen successfully
    closing = reopen_cash_day(temp_db, day_t, owner_pin="1234", reason="Customer came back late to pay")
    temp_db.commit()

    assert closing.is_closed is False
    assert closing.reopened_at is not None


def test_day_boundary_2359_vs_0001(temp_db):
    """Test that 23:59:59 IST belongs to day T and 00:00:01 IST belongs to day T+1."""
    d_oct10 = datetime(2026, 10, 10, 23, 59, 59, tzinfo=IST).astimezone(UTC)
    d_oct11 = datetime(2026, 10, 11, 0, 0, 1, tzinfo=IST).astimezone(UTC)

    t1 = create_ticket(
        db=temp_db,
        customer_phone="9820033333",
        customer_name="Boundary Tester 1",
        device_brand="Brand",
        device_model="Model",
        reported_issue="Issue",
        now=d_oct10,
    )
    add_payment(temp_db, t1, amount=700, mode="cash", kind=PaymentKind.FINAL.value, now=d_oct10)

    t2 = create_ticket(
        db=temp_db,
        customer_phone="9820044444",
        customer_name="Boundary Tester 2",
        device_brand="Brand",
        device_model="Model",
        reported_issue="Issue",
        now=d_oct11,
    )
    add_payment(temp_db, t2, amount=800, mode="cash", kind=PaymentKind.FINAL.value, now=d_oct11)
    temp_db.commit()

    # Check Day Oct 10
    sum_oct10 = compute_day_cash_summary(temp_db, datetime(2026, 10, 10).date(), opening_cash=0)
    assert sum_oct10["cash_net"] == 700

    # Check Day Oct 11
    sum_oct11 = compute_day_cash_summary(temp_db, datetime(2026, 10, 11).date(), opening_cash=0)
    assert sum_oct11["cash_net"] == 800


def test_reopen_cash_day_http_route(temp_db):
    """Test HTTP POST /cash/{date}/reopen requires reason and valid PIN."""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    setting.admin_password_hash = hash_secret("admin123")
    setting.setup_completed = True
    temp_db.commit()

    day_t = business_date()
    close_cash_day(temp_db, day_t, opening_cash=0, counted_cash=3000)
    temp_db.commit()

    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, follow_redirects=False) as client:
        # Log in
        login_res = client.post("/login", data={"password": "admin123"})
        assert login_res.status_code == 303

        # Get cash page to fetch CSRF token
        page_res = client.get(f"/cash?date={day_t.isoformat()}")
        assert page_res.status_code == 200
        import re
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', page_res.text)
        csrf_token = m.group(1) if m else ""

        # Reopen without reason should fail with 422
        bad_res = client.post(
            f"/cash/{day_t.isoformat()}/reopen",
            data={
                "csrf_token": csrf_token,
                "owner_pin": "1234",
                "reason": "",
            },
        )
        assert bad_res.status_code == 422

        # Reopen with wrong PIN should fail with 403
        wrong_pin_res = client.post(
            f"/cash/{day_t.isoformat()}/reopen",
            data={
                "csrf_token": csrf_token,
                "owner_pin": "9999",
                "reason": "Late cash payment received",
            },
        )
        assert wrong_pin_res.status_code == 403

        # Reopen with valid PIN and reason should succeed (303 redirect)
        ok_res = client.post(
            f"/cash/{day_t.isoformat()}/reopen",
            data={
                "csrf_token": csrf_token,
                "owner_pin": "1234",
                "reason": "Late cash payment received from customer",
            },
        )
        assert ok_res.status_code == 303
        assert ok_res.headers["location"] == f"/cash?date={day_t.isoformat()}"

    app.dependency_overrides.clear()

