from datetime import datetime

from sqlalchemy.orm import Session

from app.models.settings import Settings as SettingsModel
from app.security import hash_secret, verify_secret
from app.services.audit import record_audit
from app.services.errors import PinRequired, ValidationFailed
from app.timeutil import utc_now


def get_settings_model(db: Session) -> SettingsModel:
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting:
        setting = SettingsModel(id=1)
        db.add(setting)
        db.flush()
    return setting


def update_shop_details(
    db: Session,
    shop_name: str,
    shop_phone: str,
    shop_address: str,
    default_warranty_days: int,
    ticket_no_prefix: str,
    now: datetime | None = None,
) -> SettingsModel:
    current_time = now or utc_now()
    setting = get_settings_model(db)

    shop_name = shop_name.strip()
    if not shop_name or len(shop_name) > 100:
        raise ValidationFailed("Shop name must be between 1 and 100 characters")

    if not (0 <= default_warranty_days <= 365):
        raise ValidationFailed("Warranty days must be between 0 and 365")

    prefix = ticket_no_prefix.strip()
    if not prefix or len(prefix) > 10:
        raise ValidationFailed("Ticket prefix must be between 1 and 10 characters")

    changes = {}
    if setting.shop_name != shop_name:
        changes["shop_name"] = {"old": setting.shop_name, "new": shop_name}
        setting.shop_name = shop_name

    if setting.shop_phone != shop_phone.strip():
        changes["shop_phone"] = {"old": setting.shop_phone, "new": shop_phone.strip()}
        setting.shop_phone = shop_phone.strip()

    if setting.shop_address != shop_address.strip():
        changes["shop_address"] = {"old": setting.shop_address, "new": shop_address.strip()}
        setting.shop_address = shop_address.strip()

    if setting.default_warranty_days != default_warranty_days:
        changes["default_warranty_days"] = {"old": setting.default_warranty_days, "new": default_warranty_days}
        setting.default_warranty_days = default_warranty_days

    if setting.ticket_no_prefix != prefix:
        changes["ticket_no_prefix"] = {"old": setting.ticket_no_prefix, "new": prefix}
        setting.ticket_no_prefix = prefix

    if changes:
        setting.updated_at = current_time
        record_audit(
            db=db,
            entity="settings",
            entity_id=1,
            action="update",
            changed_fields=changes,
            reason="Shop details updated",
            now=current_time,
        )

    return setting


def update_receipt_and_templates(
    db: Session,
    receipt_terms_text: str,
    msg_template_intake: str,
    msg_template_ready: str,
    now: datetime | None = None,
) -> SettingsModel:
    current_time = now or utc_now()
    setting = get_settings_model(db)

    terms = receipt_terms_text.strip()
    intake_msg = msg_template_intake.strip()
    ready_msg = msg_template_ready.strip()

    if not terms or not intake_msg or not ready_msg:
        raise ValidationFailed("Receipt terms and message templates cannot be empty")

    changes = {}
    if setting.receipt_terms_text != terms:
        changes["receipt_terms_text"] = {"old": setting.receipt_terms_text, "new": terms}
        setting.receipt_terms_text = terms

    if setting.msg_template_intake != intake_msg:
        changes["msg_template_intake"] = {"old": setting.msg_template_intake, "new": intake_msg}
        setting.msg_template_intake = intake_msg

    if setting.msg_template_ready != ready_msg:
        changes["msg_template_ready"] = {"old": setting.msg_template_ready, "new": ready_msg}
        setting.msg_template_ready = ready_msg

    if changes:
        setting.updated_at = current_time
        record_audit(
            db=db,
            entity="settings",
            entity_id=1,
            action="update",
            changed_fields=changes,
            reason="Receipt terms & templates updated",
            now=current_time,
        )

    return setting


def change_shop_pin(
    db: Session,
    current_pin: str,
    new_pin: str,
    now: datetime | None = None,
) -> None:
    current_time = now or utc_now()
    setting = get_settings_model(db)

    current_pin = current_pin.strip()
    matches_admin = verify_secret(setting.admin_password_hash, current_pin)
    matches_owner = verify_secret(setting.owner_pin_hash, current_pin)
    if not (matches_admin or matches_owner):
        raise PinRequired("Current Shop PIN is incorrect")

    clean_new = new_pin.strip()
    if not (clean_new.isdigit() and 4 <= len(clean_new) <= 6):
        raise ValidationFailed("New Shop PIN must be 4 to 6 numeric digits")

    shared_pin_hash = hash_secret(clean_new)
    setting.admin_password_hash = shared_pin_hash
    setting.owner_pin_hash = shared_pin_hash
    setting.updated_at = current_time
    record_audit(
        db=db,
        entity="settings",
        entity_id=1,
        action="update",
        changed_fields={"shop_pin": {"changed": True}},
        reason="Shop PIN changed",
        now=current_time,
    )


def change_password(
    db: Session,
    current_password: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    """Compatibility wrapper; password changes now update the shared Shop PIN."""
    try:
        change_shop_pin(db, current_pin=current_password, new_pin=new_password, now=now)
    except PinRequired as exc:
        raise ValidationFailed("Current Shop PIN is incorrect") from exc


def change_owner_pin(
    db: Session,
    current_pin: str,
    new_pin: str,
    now: datetime | None = None,
) -> None:
    """Compatibility wrapper that keeps both legacy credential hashes in sync."""
    change_shop_pin(db, current_pin=current_pin, new_pin=new_pin, now=now)
