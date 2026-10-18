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
    supplier_id: int | None = None,
    owner_pin: str | None = None,
    inventory_item_id: int | None = None,
    now: datetime | None = None,
    bypass_pin: bool = False,
) -> TicketItem:
    """Add a line item (labor or part) to a ticket."""
    current_time = now or utc_now()

    # If ticket is delivered, PIN required (A-10)
    if ticket.status == TicketStatus.DELIVERED.value and not bypass_pin:
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

    linked_inv_id = None
    if item_type == ItemType.LABOR.value:
        cost_price = 0
        supplier_name = None
        supplier_id = None
    else:
        if cost_price < 0 or cost_price > 10_00_000:
            raise ValidationFailed("Cost price must be between 0 and ₹10,00,000")
        supplier_name = supplier_name.strip() if supplier_name else None

        # Check and link inventory item if selected
        if inventory_item_id:
            from app.services.inventory import adjust_inventory_stock, get_inventory_item

            inv_item = get_inventory_item(db, inventory_item_id)
            if not inv_item:
                raise ValidationFailed("Selected inventory item not found")
            if inv_item.quantity <= 0:
                raise ValidationFailed(f"Spare part '{inv_item.spare_type.title()} ({inv_item.model})' is out of stock")

            if cost_price == 0 and inv_item.cost_price > 0:
                cost_price = inv_item.cost_price
            if not supplier_name and inv_item.supplier_name:
                supplier_name = inv_item.supplier_name
            if not supplier_id and inv_item.supplier_id:
                supplier_id = inv_item.supplier_id

            adjust_inventory_stock(
                db=db,
                item=inv_item,
                delta=-1,
                reason=f"Used in ticket {ticket.ticket_no}",
                now=current_time,
            )
            linked_inv_id = inv_item.id

        # Resolve or match supplier
        if supplier_id:
            from app.services.suppliers import get_supplier
            sup = get_supplier(db, supplier_id)
            if sup:
                supplier_name = sup.name
                supplier_id = sup.id
            else:
                supplier_id = None
        elif supplier_name:
            from app.services.suppliers import get_supplier_by_name
            sup = get_supplier_by_name(db, supplier_name)
            if sup:
                supplier_id = sup.id
                supplier_name = sup.name

    item = TicketItem(
        ticket_id=ticket.id,
        ticket=ticket,
        type=item_type,
        description=description,
        price_charged=price_charged,
        cost_price=cost_price,
        supplier_name=supplier_name,
        supplier_id=supplier_id,
        inventory_item_id=linked_inv_id,
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
    supplier_id: int | None = None,
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
        supplier_id = None
    else:
        if cost_price < 0:
            raise ValidationFailed("Cost price must be >= 0")
        supplier_name = supplier_name.strip() if supplier_name else None

        if supplier_id:
            from app.services.suppliers import get_supplier
            sup = get_supplier(db, supplier_id)
            if sup:
                supplier_name = sup.name
                supplier_id = sup.id
            else:
                supplier_id = None
        elif supplier_name:
            from app.services.suppliers import get_supplier_by_name
            sup = get_supplier_by_name(db, supplier_name)
            if sup:
                supplier_id = sup.id
                supplier_name = sup.name

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
    if item.supplier_id != supplier_id:
        changes["supplier_id"] = {"old": item.supplier_id, "new": supplier_id}
        item.supplier_id = supplier_id

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
    if item.is_deleted:
        return item

    ticket = item.ticket
    if ticket.status == TicketStatus.DELIVERED.value:
        setting = db.query(SettingsModel).filter_by(id=1).first()
        if not owner_pin or not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, owner_pin.strip()):
            raise PinRequired("Modifying items on a delivered ticket requires the Owner PIN.")

    item.is_deleted = True
    item.updated_at = current_time

    if item.inventory_item_id and item.type == ItemType.PART.value:
        from app.services.inventory import adjust_inventory_stock, get_inventory_item

        inv_item = get_inventory_item(db, item.inventory_item_id)
        if inv_item:
            adjust_inventory_stock(
                db=db,
                item=inv_item,
                delta=1,
                reason=f"Replenished from deleted line item on ticket {ticket.ticket_no}",
                now=current_time,
            )

    record_audit(
        db=db,
        entity="item",
        entity_id=item.id,
        ticket_id=ticket.id,
        action="delete",
        now=current_time,
    )

    db.flush()
    return item
