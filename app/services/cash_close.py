from datetime import date, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.cash_closing import CashClosing
from app.models.enums import PaymentMode
from app.models.payment import Payment
from app.models.settings import Settings as SettingsModel
from app.security import verify_secret
from app.services.audit import record_audit
from app.services.errors import PinRequired, ValidationFailed
from app.timeutil import business_date, ist_day_to_utc_bounds, utc_now


def get_default_opening_cash(db: Session, target_date: date) -> int:
    """Return counted_cash of the most recent closed day before target_date, or 0."""
    prev = (
        db.query(CashClosing)
        .filter(CashClosing.date < target_date)
        .order_by(desc(CashClosing.date))
        .first()
    )
    if prev:
        return prev.counted_cash
    return 0


def get_day_payments(db: Session, target_date: date) -> list[Payment]:
    """Get all non-deleted payments whose paid_at falls within the IST target_date."""
    start_utc, end_utc = ist_day_to_utc_bounds(target_date)
    return (
        db.query(Payment)
        .filter(
            Payment.is_deleted.is_(False),
            Payment.paid_at >= start_utc,
            Payment.paid_at <= end_utc,
        )
        .order_by(Payment.paid_at.asc())
        .all()
    )


def compute_day_cash_summary(db: Session, target_date: date, opening_cash: int) -> dict:
    """Compute payments grouped by mode and expected cash for an IST date."""
    payments = get_day_payments(db, target_date)

    cash_payments = [p for p in payments if p.mode == PaymentMode.CASH.value]
    card_payments = [p for p in payments if p.mode == PaymentMode.CARD.value]
    upi_payments = [p for p in payments if p.mode == PaymentMode.UPI.value]

    cash_net = sum(p.amount for p in cash_payments)
    card_net = sum(p.amount for p in card_payments)
    upi_net = sum(p.amount for p in upi_payments)

    expected_cash = opening_cash + cash_net

    return {
        "payments": payments,
        "cash_payments": cash_payments,
        "card_payments": card_payments,
        "upi_payments": upi_payments,
        "cash_net": cash_net,
        "card_net": card_net,
        "upi_net": upi_net,
        "expected_cash": expected_cash,
    }


def close_cash_day(
    db: Session,
    target_date: date,
    opening_cash: int,
    counted_cash: int,
    note: str | None = None,
    now: datetime | None = None,
) -> CashClosing:
    """Close an IST cash day."""
    current_time = now or utc_now()
    if target_date > business_date(current_time):
        raise ValidationFailed("Cannot close a future date")

    if opening_cash < 0 or counted_cash < 0:
        raise ValidationFailed("Opening and counted cash must be non-negative")

    summary = compute_day_cash_summary(db, target_date, opening_cash)
    expected_cash = summary["expected_cash"]
    variance = counted_cash - expected_cash

    closing = db.query(CashClosing).filter_by(date=target_date).first()
    if not closing:
        closing = CashClosing(date=target_date)
        db.add(closing)

    closing.opening_cash = opening_cash
    closing.expected_cash = expected_cash
    closing.counted_cash = counted_cash
    closing.variance = variance
    closing.note = note.strip() if note else None
    closing.is_closed = True
    closing.closed_at = current_time
    closing.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity="cash_closing",
        entity_id=closing.id,
        action="update",
        changed_fields={
            "expected_cash": {"new": expected_cash},
            "counted_cash": {"new": counted_cash},
            "variance": {"new": variance},
            "is_closed": {"new": True},
        },
        reason=f"Closed day {target_date.isoformat()}",
        now=current_time,
    )

    return closing


def reopen_cash_day(
    db: Session,
    target_date: date,
    owner_pin: str,
    reason: str | None = None,
    now: datetime | None = None,
) -> CashClosing:
    """Reopen a closed cash day with owner PIN and mandatory reason."""
    current_time = now or utc_now()

    if not reason or not reason.strip():
        raise ValidationFailed("Reopen reason is required")

    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
        raise PinRequired("Invalid owner PIN")

    closing = db.query(CashClosing).filter_by(date=target_date).first()
    if not closing or not closing.is_closed:
        raise ValidationFailed("Day is not currently closed")

    closing.is_closed = False
    closing.reopened_at = current_time
    closing.updated_at = current_time

    record_audit(
        db=db,
        entity="cash_closing",
        entity_id=closing.id,
        action="update",
        changed_fields={"is_closed": {"old": True, "new": False}},
        reason=f"Reopened day {target_date.isoformat()}: {reason.strip()}",
        now=current_time,
    )

    return closing
