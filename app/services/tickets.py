from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.formatting import normalize_phone
from app.models.customer import Customer
from app.models.enums import PaymentKind, PaymentMode, TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.security import decrypt_passcode, encrypt_passcode, verify_secret
from app.services.audit import record_audit
from app.services.errors import DayClosed, PinRequired, ValidationFailed
from app.services.payments import add_payment, is_cash_day_closed
from app.timeutil import business_date, utc_now


def generate_ticket_number(db: Session) -> str:
    """Generate sequential unique ticket number."""
    setting = db.query(SettingsModel).filter_by(id=1).with_for_update().first()
    if not setting:
        setting = SettingsModel(id=1)
        db.add(setting)
        db.flush()

    ticket_no = f"{setting.ticket_no_prefix}-{setting.next_ticket_seq}"
    setting.next_ticket_seq += 1
    return ticket_no


def get_or_create_customer(
    db: Session,
    phone_raw: str,
    name: str,
    now: datetime | None = None,
) -> tuple[Customer, bool]:
    """Look up customer by normalized phone; update name if changed."""
    current_time = now or utc_now()
    phone = normalize_phone(phone_raw)
    name = name.strip()
    if not name or len(name) > 100:
        raise ValidationFailed("Customer name must be between 1 and 100 characters")

    customer = db.query(Customer).filter_by(phone=phone).first()
    if not customer:
        customer = Customer(phone=phone, name=name)
        db.add(customer)
        db.flush()
        record_audit(
            db=db,
            entity="customer",
            entity_id=customer.id,
            action="create",
            changed_fields={"name": {"old": None, "new": name}, "phone": {"old": None, "new": phone}},
            now=current_time,
        )
        return customer, True

    if customer.name != name:
        old_name = customer.name
        customer.name = name
        customer.updated_at = current_time
        record_audit(
            db=db,
            entity="customer",
            entity_id=customer.id,
            action="update",
            changed_fields={"name": {"old": old_name, "new": name}},
            reason="Customer name updated during intake",
            now=current_time,
        )

    return customer, False


def create_ticket(
    db: Session,
    customer_phone: str,
    customer_name: str,
    device_brand: str,
    device_model: str,
    reported_issue: str,
    issue_category: str = "Other",
    imei_or_serial: str | None = None,
    color: str | None = None,
    passcode: str | None = None,
    estimate_amount: int | None = None,
    intake_condition: dict[str, Any] | None = None,
    advance_amount: int = 0,
    advance_mode: str = PaymentMode.CASH.value,
    advance_note: str | None = None,
    parent_ticket_id: int | None = None,
    now: datetime | None = None,
) -> Ticket:
    """Create a new ticket and optional advance payment atomically."""
    current_time = now or utc_now()

    # Pre-check: if advance payment requested, verify cash day is open
    if advance_amount > 0:
        today_ist = business_date(current_time)
        if is_cash_day_closed(db, today_ist):
            raise DayClosed("Today's cash is closed. Reopen cash with owner PIN before creating ticket with advance payment.")

    customer, _ = get_or_create_customer(db, customer_phone, customer_name, now=current_time)

    # Validations
    device_brand = device_brand.strip().strip("'\"\\").strip()
    device_model = device_model.strip().strip("'\"\\").strip()
    reported_issue = reported_issue.strip()

    if not device_brand or len(device_brand) > 60:
        raise ValidationFailed("Device brand must be between 1 and 60 characters")
    if not device_model or len(device_model) > 60:
        raise ValidationFailed("Device model must be between 1 and 60 characters")
    if not reported_issue or len(reported_issue) < 3 or len(reported_issue) > 1000:
        raise ValidationFailed("Reported issue must be between 3 and 1000 characters")

    setting = db.query(SettingsModel).filter_by(id=1).first()
    default_warranty = setting.default_warranty_days if setting else 30
    ticket_no = generate_ticket_number(db)

    condition = intake_condition or {
        "screen_cracked": False,
        "powers_on": True,
        "water_damage_indicator": False,
        "back_cover_damaged": False,
        "sim_left": False,
        "memory_card_left": False,
        "charger_accessories_received": False,
        "accessories_note": "",
        "notes": "",
    }

    ticket = Ticket(
        ticket_no=ticket_no,
        customer_id=customer.id,
        device_brand=device_brand,
        device_model=device_model,
        imei_or_serial=imei_or_serial.strip() if imei_or_serial else None,
        color=color.strip() if color else None,
        passcode_encrypted=encrypt_passcode(passcode.strip()) if passcode else None,
        reported_issue=reported_issue,
        issue_category=issue_category,
        intake_condition=condition,
        estimate_amount=estimate_amount if (estimate_amount and estimate_amount >= 0) else None,
        status=TicketStatus.RECEIVED.value,
        warranty_days=default_warranty,
        parent_ticket_id=parent_ticket_id,
        received_at=current_time,
        is_deleted=False,
    )
    db.add(ticket)
    db.flush()

    # Initial status history row
    history = StatusHistory(
        ticket_id=ticket.id,
        from_status=None,
        to_status=TicketStatus.RECEIVED.value,
        changed_at=current_time,
        note="Ticket created at intake",
    )
    db.add(history)

    # Audit ticket creation
    record_audit(
        db=db,
        entity="ticket",
        entity_id=ticket.id,
        ticket_id=ticket.id,
        action="create",
        changed_fields={"ticket_no": {"old": None, "new": ticket_no}},
        now=current_time,
    )

    # Optional advance payment
    if advance_amount > 0:
        add_payment(
            db=db,
            ticket=ticket,
            amount=advance_amount,
            mode=advance_mode,
            kind=PaymentKind.ADVANCE.value,
            note=advance_note,
            confirm_overpay=True,
            now=current_time,
        )


    return ticket


def update_ticket_details(
    db: Session,
    ticket: Ticket,
    device_brand: str,
    device_model: str,
    reported_issue: str,
    issue_category: str,
    imei_or_serial: str | None = None,
    color: str | None = None,
    estimate_amount: int | None = None,
    technician_note: str | None = None,
    intake_condition: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Ticket:
    """Update ticket fields with validation and audit."""
    current_time = now or utc_now()
    changes = {}

    def track_change(field: str, old_val: Any, new_val: Any):
        if old_val != new_val:
            changes[field] = {"old": old_val, "new": new_val}

    clean_brand = device_brand.strip().strip("'\"\\").strip()
    track_change("device_brand", ticket.device_brand, clean_brand)
    ticket.device_brand = clean_brand

    clean_model = device_model.strip().strip("'\"\\").strip()
    track_change("device_model", ticket.device_model, clean_model)
    ticket.device_model = clean_model

    track_change("reported_issue", ticket.reported_issue, reported_issue.strip())
    ticket.reported_issue = reported_issue.strip()

    track_change("issue_category", ticket.issue_category, issue_category)
    ticket.issue_category = issue_category

    new_imei = imei_or_serial.strip() if imei_or_serial else None
    track_change("imei_or_serial", ticket.imei_or_serial, new_imei)
    ticket.imei_or_serial = new_imei

    new_color = color.strip() if color else None
    track_change("color", ticket.color, new_color)
    ticket.color = new_color

    track_change("estimate_amount", ticket.estimate_amount, estimate_amount)
    ticket.estimate_amount = estimate_amount

    new_tech_note = technician_note.strip() if technician_note else None
    track_change("technician_note", ticket.technician_note, new_tech_note)
    ticket.technician_note = new_tech_note

    if intake_condition:
        track_change("intake_condition", ticket.intake_condition, intake_condition)
        ticket.intake_condition = intake_condition

    if changes:
        ticket.updated_at = current_time
        record_audit(
            db=db,
            entity="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            action="update",
            changed_fields=changes,
            now=current_time,
        )

    return ticket


def delete_ticket(
    db: Session,
    ticket: Ticket,
    reason: str,
    owner_pin: str,
    now: datetime | None = None,
) -> Ticket:
    """Soft delete ticket with owner PIN and reason. Blocked if any active payments exist."""
    current_time = now or utc_now()

    # Blocked if has non-deleted payment (A-11)
    active_payments = [p for p in ticket.payments if not p.is_deleted]
    if active_payments:
        raise ValidationFailed(
            f"Cannot delete ticket {ticket.ticket_no} because it has {len(active_payments)} active payment(s). "
            "Refund or delete all payments first."
        )

    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
        raise PinRequired("Invalid owner PIN")

    if not reason or len(reason.strip()) < 3:
        raise ValidationFailed("Delete reason must be at least 3 characters")

    ticket.is_deleted = True
    ticket.deleted_reason = reason.strip()
    ticket.deleted_at = current_time
    ticket.updated_at = current_time

    record_audit(
        db=db,
        entity="ticket",
        entity_id=ticket.id,
        ticket_id=ticket.id,
        action="delete",
        reason=reason.strip(),
        now=current_time,
    )

    return ticket


def reveal_ticket_passcode(db: Session, ticket: Ticket, now: datetime | None = None) -> str | None:
    """Decrypt passcode for display and record viewed audit."""
    current_time = now or utc_now()
    if not ticket.passcode_encrypted:
        return None

    record_audit(
        db=db,
        entity="ticket",
        entity_id=ticket.id,
        ticket_id=ticket.id,
        action="update",
        changed_fields={"passcode_viewed": {"changed": True}},
        reason="Passcode revealed by user",
        now=current_time,
    )
    return decrypt_passcode(ticket.passcode_encrypted)


def clear_ticket_passcode(db: Session, ticket: Ticket, now: datetime | None = None) -> None:
    """Clear device passcode."""
    current_time = now or utc_now()
    ticket.passcode_encrypted = None
    ticket.updated_at = current_time
    record_audit(
        db=db,
        entity="ticket",
        entity_id=ticket.id,
        ticket_id=ticket.id,
        action="update",
        changed_fields={"passcode_cleared": {"changed": True}},
        reason="Passcode cleared",
        now=current_time,
    )
