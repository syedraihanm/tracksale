from datetime import timedelta

import pytest

from app.models.enums import Outcome, TicketStatus
from app.services.errors import InvalidTransition, NeedsConfirmation
from app.services.items import add_item
from app.services.payments import add_payment
from app.services.status import VALID_TRANSITIONS, transition_ticket
from app.services.tickets import create_ticket
from app.timeutil import business_date, utc_now


def test_transition_matrix(temp_db):
    """Test every cell in the 8x8 status matrix matches VALID_TRANSITIONS."""
    all_statuses = [s.value for s in TicketStatus]

    for from_s in all_statuses:
        for to_s in all_statuses:
            # Create a ticket
            ticket = create_ticket(
                db=temp_db,
                customer_phone="9820011111",
                customer_name="Matrix Tester",
                device_brand="Brand",
                device_model="Model",
                reported_issue="Issue",
            )
            # Manually set status to from_s for matrix testing
            ticket.status = from_s
            temp_db.commit()

            is_valid = to_s in VALID_TRANSITIONS.get(from_s, set())
            if is_valid:
                # Valid transition should succeed (providing confirm_pending_balance=True if going to delivered)
                transition_ticket(temp_db, ticket, to_s, confirm_pending_balance=True)
                assert ticket.status == to_s
            else:
                # Invalid transition must raise InvalidTransition
                with pytest.raises(InvalidTransition):
                    transition_ticket(temp_db, ticket, to_s, confirm_pending_balance=True)


def test_delivery_gate_pending_balance(temp_db):
    """Delivery with positive balance requires explicit confirmation."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820022222",
        customer_name="Balance Tester",
        device_brand="Samsung",
        device_model="S20",
        reported_issue="Broken screen",
    )
    add_item(temp_db, ticket, item_type="labor", description="Screen repair", price_charged=2000)
    transition_ticket(temp_db, ticket, TicketStatus.IN_PROGRESS.value)
    transition_ticket(temp_db, ticket, TicketStatus.READY_FOR_PICKUP.value)

    # Attempt to deliver without confirmation when balance is ₹2000
    with pytest.raises(NeedsConfirmation) as exc:
        transition_ticket(temp_db, ticket, TicketStatus.DELIVERED.value, confirm_pending_balance=False)
    assert "₹2,000" in str(exc.value)

    # Now deliver with confirm_pending_balance=True
    transition_ticket(temp_db, ticket, TicketStatus.DELIVERED.value, confirm_pending_balance=True, note="Customer will pay tomorrow")
    assert ticket.status == TicketStatus.DELIVERED.value
    assert ticket.delivered_at is not None


def test_outcome_and_warranty_on_delivery(temp_db):
    """Verify outcome and warranty are properly computed upon delivery."""
    # 1. Repaired ticket
    t_rep = create_ticket(
        db=temp_db,
        customer_phone="9820033333",
        customer_name="Repair Tester",
        device_brand="Apple",
        device_model="iPhone 13",
        reported_issue="Battery replacement",
    )
    add_item(temp_db, t_rep, item_type="labor", description="Battery replacement", price_charged=1500)
    add_payment(temp_db, t_rep, amount=1500, mode="cash", kind="final")
    transition_ticket(temp_db, t_rep, TicketStatus.IN_PROGRESS.value)
    transition_ticket(temp_db, t_rep, TicketStatus.READY_FOR_PICKUP.value)
    now = utc_now()
    transition_ticket(temp_db, t_rep, TicketStatus.DELIVERED.value, now=now)

    assert t_rep.outcome == Outcome.REPAIRED.value
    assert t_rep.warranty_until == business_date(now) + timedelta(days=t_rep.warranty_days)

    # 2. Unrepairable ticket
    t_unrep = create_ticket(
        db=temp_db,
        customer_phone="9820044444",
        customer_name="Unrepairable Tester",
        device_brand="OnePlus",
        device_model="9 Pro",
        reported_issue="Water damage",
    )
    transition_ticket(temp_db, t_unrep, TicketStatus.UNREPAIRABLE.value)
    transition_ticket(temp_db, t_unrep, TicketStatus.DELIVERED.value, confirm_pending_balance=True)

    assert t_unrep.outcome == Outcome.UNREPAIRABLE.value
    assert t_unrep.warranty_until is None

    # 3. Declined ticket
    t_dec = create_ticket(
        db=temp_db,
        customer_phone="9820055555",
        customer_name="Declined Tester",
        device_brand="Xiaomi",
        device_model="Redmi Note 10",
        reported_issue="Display replacement",
    )
    transition_ticket(temp_db, t_dec, TicketStatus.DECLINED.value)
    transition_ticket(temp_db, t_dec, TicketStatus.DELIVERED.value, confirm_pending_balance=True)

    assert t_dec.outcome == Outcome.DECLINED.value
    assert t_dec.warranty_until is None


def test_passcode_clear_on_delivery(temp_db):
    """Delivery can optionally clear the encrypted passcode for customer privacy."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820066666",
        customer_name="Passcode Tester",
        device_brand="Google",
        device_model="Pixel 6",
        reported_issue="Mic issue",
        passcode="9988",
    )
    assert ticket.passcode_encrypted is not None

    transition_ticket(temp_db, ticket, TicketStatus.IN_PROGRESS.value)
    transition_ticket(temp_db, ticket, TicketStatus.READY_FOR_PICKUP.value)
    transition_ticket(temp_db, ticket, TicketStatus.DELIVERED.value, confirm_pending_balance=True, clear_passcode=True)

    assert ticket.passcode_encrypted is None
