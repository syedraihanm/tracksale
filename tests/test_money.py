import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.enums import PaymentKind
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret
from app.services.cash_close import close_cash_day
from app.services.errors import (
    DayClosed,
    NeedsConfirmation,
    PinRequired,
    ValidationFailed,
)
from app.services.items import add_item
from app.services.payments import (
    add_payment,
    delete_payment,
    edit_payment,
    get_ticket_totals,
)
from app.services.tickets import create_ticket
from app.timeutil import business_date, utc_now


def test_advance_and_upi_remainder_flow(temp_db):
    """AC4: Ticket with ₹500 cash advance, items ₹2,500, balance ₹2,000 paid via UPI."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820012345",
        customer_name="Money Test",
        device_brand="Samsung",
        device_model="M31",
        reported_issue="Screen replacement",
        advance_amount=500,
        advance_mode="cash",
    )
    temp_db.commit()

    # Initial totals: items=0, net_paid=500, balance=-500
    items_tot, net_paid, bal = get_ticket_totals(ticket)
    assert items_tot == 0
    assert net_paid == 500
    assert bal == -500

    # Add labor and part
    add_item(temp_db, ticket, item_type="labor", description="Screen fitting labor", price_charged=500)
    add_item(temp_db, ticket, item_type="part", description="M31 AMOLED Screen", price_charged=2000, cost_price=1300)
    temp_db.commit()

    items_tot, net_paid, bal = get_ticket_totals(ticket)
    assert items_tot == 2500
    assert net_paid == 500
    assert bal == 2000

    # Pay remaining balance via UPI
    add_payment(temp_db, ticket, amount=2000, mode="upi", kind=PaymentKind.FINAL.value)
    temp_db.commit()

    items_tot, net_paid, bal = get_ticket_totals(ticket)
    assert items_tot == 2500
    assert net_paid == 2500
    assert bal == 0
    assert len(ticket.payments) == 2


def test_refund_constraints(temp_db):
    """Refunds must not exceed net paid, must be positive amount with reason >= 3 chars."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820023456",
        customer_name="Refund Tester",
        device_brand="Apple",
        device_model="iPhone 11",
        reported_issue="Battery replacement",
    )
    add_item(temp_db, ticket, item_type="labor", description="Battery replacement", price_charged=1500)
    add_payment(temp_db, ticket, amount=1500, mode="cash", kind=PaymentKind.FINAL.value)
    temp_db.commit()

    # Refund exceeding net paid
    with pytest.raises(ValidationFailed) as exc:
        add_payment(temp_db, ticket, amount=1600, mode="cash", kind=PaymentKind.REFUND.value, note="Over-refund attempt")
    assert "cannot exceed total paid" in str(exc.value)

    # Refund with empty or short reason
    with pytest.raises(ValidationFailed) as exc:
        add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.REFUND.value, note="  ")
    assert "Refund reason is required" in str(exc.value)

    # Valid refund of ₹500
    ref_payment = add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.REFUND.value, note="Customer compensation")
    temp_db.commit()
    assert ref_payment.amount == -500

    _, net_paid, bal = get_ticket_totals(ticket)
    assert net_paid == 1000  # 1500 - 500
    assert bal == 500


def test_overpayment_confirmation(temp_db):
    """Adding payment exceeding reference total raises NeedsConfirmation unless confirmed."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820034567",
        customer_name="Overpay Tester",
        device_brand="Vivo",
        device_model="V20",
        reported_issue="Charging port",
    )
    add_item(temp_db, ticket, item_type="labor", description="Port fix", price_charged=400)
    temp_db.commit()

    # Attempting to pay ₹500 without confirmation
    with pytest.raises(NeedsConfirmation) as exc:
        add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.FINAL.value, confirm_overpay=False)
    assert "exceeds the reference total" in str(exc.value)

    # With confirm_overpay=True
    pay = add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.FINAL.value, confirm_overpay=True)
    temp_db.commit()
    assert pay.amount == 500


def test_no_orphan_payments(temp_db):
    """AC5: Foreign key constraint forbids orphan payments with invalid ticket_id."""
    with pytest.raises(DBAPIError):
        temp_db.execute(text("INSERT INTO payments (ticket_id, amount, mode, kind, paid_at, is_deleted) VALUES (99999, 500, 'cash', 'final', '2026-10-10 10:00:00', 0)"))
        temp_db.commit()
    temp_db.rollback()


def test_day_closed_locks_payments(temp_db):
    """Payments cannot be added if the cash day is already closed."""
    # Set owner PIN in settings
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820045678",
        customer_name="Day Close Tester",
        device_brand="Realme",
        device_model="8",
        reported_issue="Screen replacement",
    )
    today = business_date(utc_now())

    # Close cash day
    close_cash_day(temp_db, today, opening_cash=0, counted_cash=0)
    temp_db.commit()

    # Attempting to add payment today should fail
    with pytest.raises(DayClosed):
        add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.FINAL.value)


def test_payment_edit_and_delete_pin_protection(temp_db):
    """Payment edit and soft delete require valid Owner PIN and audit logging."""
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820056789",
        customer_name="Edit Delete Tester",
        device_brand="Oppo",
        device_model="A53",
        reported_issue="Speaker fix",
    )
    pay = add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.FINAL.value)
    temp_db.commit()

    # Edit payment
    edit_payment(temp_db, pay, amount=400, mode="cash", note="Typo fix")
    temp_db.commit()
    assert pay.amount == 400

    # Delete without correct PIN
    with pytest.raises(PinRequired):
        delete_payment(temp_db, pay, reason="Mistake", owner_pin="wrong")

    # Delete with correct PIN
    delete_payment(temp_db, pay, reason="Duplicate billing", owner_pin="1234")
    temp_db.commit()
    assert pay.is_deleted is True

    # Direct hard DELETE via SQL trigger should fail
    with pytest.raises(DBAPIError):
        temp_db.execute(text(f"DELETE FROM payments WHERE id = {pay.id}"))
        temp_db.commit()
    temp_db.rollback()
