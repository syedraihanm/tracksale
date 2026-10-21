from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models.cash_closing import CashClosing
from app.models.enums import PaymentKind, PaymentMode
from app.models.payment import Payment
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.security import verify_secret
from app.services.audit import record_audit
from app.services.errors import (
    DayClosed,
    PinRequired,
    ValidationFailed,
)
from app.timeutil import business_date, utc_now


def is_cash_day_closed(db: Session, target_date: date) -> bool:
    closing = db.query(CashClosing).filter_by(date=target_date).first()
    return bool(closing and closing.is_closed)


def get_ticket_totals(ticket: Ticket) -> tuple[int, int, int]:
    """Calculate (customer_total, net_paid, balance_due) for a ticket.

    Item cost is tracked separately. Existing line-item charges remain the
    customer total for older tickets; otherwise the ticket estimate is used
    when one exists. A payment alone does not create a customer charge.
    """
    from sqlalchemy.orm import object_session
    s = object_session(ticket)
    if s:
        s.refresh(ticket, ["items", "payments"])
    legacy_line_charges = sum(i.price_charged for i in ticket.items if not i.is_deleted)
    customer_total = legacy_line_charges or (ticket.estimate_amount or 0)
    net_paid = sum(p.amount for p in ticket.payments if not p.is_deleted)
    # When no customer total has been entered yet, keep payments separate and
    # do not mislabel them as a credit balance against the shop's item costs.
    balance_due = customer_total - net_paid if customer_total > 0 else 0
    return customer_total, net_paid, balance_due


def add_payment(
    db: Session,
    ticket: Ticket,
    amount: int,
    mode: str,
    kind: str,
    note: str | None = None,
    confirm_overpay: bool = False,
    now: datetime | None = None,
) -> Payment:
    """Record customer money received separately from ticket item costs."""
    current_time = now or utc_now()
    payment_ist_date = business_date(current_time)

    # Check if today's cash is closed
    if is_cash_day_closed(db, payment_ist_date):
        raise DayClosed("Today's cash is closed. Reopen day with owner PIN to record new payments.")

    if mode not in (PaymentMode.CASH.value, PaymentMode.CARD.value, PaymentMode.UPI.value):
        raise ValidationFailed("Payment mode must be cash, card, or upi")

    if kind not in (PaymentKind.ADVANCE.value, PaymentKind.FINAL.value, PaymentKind.REFUND.value):
        raise ValidationFailed("Payment kind must be advance, final, or refund")

    # Refund handling
    if kind == PaymentKind.REFUND.value:
        if amount <= 0:
            raise ValidationFailed("Refund amount must be greater than zero")
        if not note or len(note.strip()) < 3:
            raise ValidationFailed("Refund reason is required (at least 3 characters)")
        if amount > net_paid:
            raise ValidationFailed(f"Refund amount (₹{amount}) cannot exceed total paid to date (₹{net_paid})")

        stored_amount = -abs(amount)
        audit_reason = note.strip()
    else:
        # Advance or final payment
        if amount <= 0:
            raise ValidationFailed("Payment amount must be greater than zero")
        if amount > 10_00_000:
            raise ValidationFailed("Payment amount exceeds sanity cap of ₹10,00,000")

        stored_amount = amount
        audit_reason = None

    payment = Payment(
        ticket_id=ticket.id,
        ticket=ticket,
        amount=stored_amount,
        mode=mode,
        kind=kind,
        paid_at=current_time,
        note=note.strip() if note else None,
        is_deleted=False,
    )
    db.add(payment)
    db.flush()

    record_audit(
        db=db,
        entity="payment",
        entity_id=payment.id,
        ticket_id=ticket.id,
        action="create",
        changed_fields={
            "amount": {"old": None, "new": stored_amount},
            "mode": {"old": None, "new": mode},
            "kind": {"old": None, "new": kind},
        },
        reason=audit_reason,
        now=current_time,
    )

    return payment


def edit_payment(
    db: Session,
    payment: Payment,
    amount: int,
    mode: str,
    note: str | None = None,
    now: datetime | None = None,
) -> Payment:
    """Edit payment amount, mode, note if the payment day is not closed."""
    current_time = now or utc_now()
    pay_date = business_date(payment.paid_at)

    if is_cash_day_closed(db, pay_date):
        raise DayClosed("Payment day is closed. Reopen day with owner PIN to modify.")

    if payment.is_deleted:
        raise ValidationFailed("Cannot edit a deleted payment")

    if mode not in (PaymentMode.CASH.value, PaymentMode.CARD.value, PaymentMode.UPI.value):
        raise ValidationFailed("Invalid payment mode")

    if payment.kind == PaymentKind.REFUND.value:
        if amount <= 0:
            raise ValidationFailed("Refund amount must be positive")
        new_amount = -abs(amount)
    else:
        if amount <= 0:
            raise ValidationFailed("Payment amount must be positive")
        new_amount = abs(amount)

    changes = {}
    if payment.amount != new_amount:
        changes["amount"] = {"old": payment.amount, "new": new_amount}
        payment.amount = new_amount

    if payment.mode != mode:
        changes["mode"] = {"old": payment.mode, "new": mode}
        payment.mode = mode

    new_note = note.strip() if note else None
    if payment.note != new_note:
        changes["note"] = {"old": payment.note, "new": new_note}
        payment.note = new_note

    if changes:
        payment.updated_at = current_time
        record_audit(
            db=db,
            entity="payment",
            entity_id=payment.id,
            ticket_id=payment.ticket_id,
            action="update",
            changed_fields=changes,
            now=current_time,
        )

    return payment


def delete_payment(
    db: Session,
    payment: Payment,
    reason: str,
    owner_pin: str,
    now: datetime | None = None,
) -> Payment:
    """Soft delete a payment with owner PIN and reason."""
    current_time = now or utc_now()
    pay_date = business_date(payment.paid_at)

    if is_cash_day_closed(db, pay_date):
        raise DayClosed("Payment day is closed. Reopen day with owner PIN before deleting.")

    # Verify PIN
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
        raise PinRequired("Invalid owner PIN")

    if not reason or len(reason.strip()) < 3:
        raise ValidationFailed("Delete reason must be at least 3 characters")

    payment.is_deleted = True
    payment.deleted_reason = reason.strip()
    payment.deleted_at = current_time
    payment.updated_at = current_time

    record_audit(
        db=db,
        entity="payment",
        entity_id=payment.id,
        ticket_id=payment.ticket_id,
        action="delete",
        reason=reason.strip(),
        now=current_time,
    )

    return payment
