from datetime import datetime

from sqlalchemy.orm import Session

from app.models.enums import ItemType, TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.security import verify_secret
from app.services.audit import record_audit
from app.services.errors import PinRequired, ValidationFailed
from app.timeutil import utc_now


def add_item(
    db: Session,
    ticket: Ticket,
    item_type: str,
    description: str,
    price_charged: int,
    cost_price: int = 0,
    supplier_name: str | None = None,
    owner_pin: str | None = None,
    now: datetime | None = None,
) -> TicketItem:
    """Add a line item (labor or part) to a ticket."""
    current_time = now or utc_now()

    # If ticket is delivered, PIN required (A-10)
    if ticket.status == TicketStatus.DELIVERED.value:
        setting = db.query(SettingsModel).filter_by(id=1).first()
        if not owner_pin or not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
            raise PinRequired("Modifying items on a delivered ticket requires the Owner PIN.")

    description = description.strip()
    if not description or len(description) > 120:
        raise ValidationFailed("Item description must be between 1 and 120 characters")

    if price_charged < 0 or price_charged > 10_00_000:
        raise ValidationFailed("Price charged must be between 0 and ₹10,00,000")

    if item_type not in (ItemType.LABOR.value, ItemType.PART.value):
        raise ValidationFailed("Item type must be labor or part")

    if item_type == ItemType.LABOR.value:
        cost_price = 0
        supplier_name = None
    else:
        if cost_price < 0 or cost_price > 10_00_000:
            raise ValidationFailed("Cost price must be between 0 and ₹10,00,000")
        supplier_name = supplier_name.strip() if supplier_name else None

    item = TicketItem(
        ticket_id=ticket.id,
        ticket=ticket,
        type=item_type,
        description=description,
        price_charged=price_charged,
        cost_price=cost_price,
        supplier_name=supplier_name,
        is_deleted=False,
    )
    db.add(item)
    db.flush()

    record_audit(
        db=db,
        entity="item",
        entity_id=item.id,
        ticket_id=ticket.id,
        action="create",
        changed_fields={
            "description": {"old": None, "new": description},
            "price_charged": {"old": None, "new": price_charged},
            "type": {"old": None, "new": item_type},
        },
        now=current_time,
    )

    return item


def edit_item(
    db: Session,
    item: TicketItem,
    description: str,
    price_charged: int,
    cost_price: int = 0,
    supplier_name: str | None = None,
    owner_pin: str | None = None,
    now: datetime | None = None,
) -> TicketItem:
    """Edit a line item."""
    current_time = now or utc_now()
    ticket = item.ticket

    if ticket.status == TicketStatus.DELIVERED.value:
        setting = db.query(SettingsModel).filter_by(id=1).first()
        if not owner_pin or not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
            raise PinRequired("Modifying items on a delivered ticket requires the Owner PIN.")

    description = description.strip()
    if not description or len(description) > 120:
        raise ValidationFailed("Description must be between 1 and 120 characters")

    if price_charged < 0:
        raise ValidationFailed("Price charged must be >= 0")

    if item.type == ItemType.LABOR.value:
        cost_price = 0
        supplier_name = None
    else:
        if cost_price < 0:
            raise ValidationFailed("Cost price must be >= 0")
        supplier_name = supplier_name.strip() if supplier_name else None

    changes = {}
    if item.description != description:
        changes["description"] = {"old": item.description, "new": description}
        item.description = description
    if item.price_charged != price_charged:
        changes["price_charged"] = {"old": item.price_charged, "new": price_charged}
        item.price_charged = price_charged
    if item.cost_price != cost_price:
        changes["cost_price"] = {"old": item.cost_price, "new": cost_price}
        item.cost_price = cost_price
    if item.supplier_name != supplier_name:
        changes["supplier_name"] = {"old": item.supplier_name, "new": supplier_name}
        item.supplier_name = supplier_name

    if changes:
        item.updated_at = current_time
        record_audit(
            db=db,
            entity="item",
            entity_id=item.id,
            ticket_id=ticket.id,
            action="update",
            changed_fields=changes,
            now=current_time,
        )

    return item


def delete_item(
    db: Session,
    item: TicketItem,
    owner_pin: str | None = None,
    now: datetime | None = None,
) -> TicketItem:
    """Soft delete an item."""
    current_time = now or utc_now()
    ticket = item.ticket

    if ticket.status == TicketStatus.DELIVERED.value:
        setting = db.query(SettingsModel).filter_by(id=1).first()
        if not owner_pin or not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
            raise PinRequired("Modifying items on a delivered ticket requires the Owner PIN.")

    item.is_deleted = True
    item.updated_at = current_time

    record_audit(
        db=db,
        entity="item",
        entity_id=item.id,
        ticket_id=ticket.id,
        action="delete",
        now=current_time,
    )

    return item
