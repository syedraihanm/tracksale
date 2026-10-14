from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, AuditEntity
from app.models.inventory import InventoryItem
from app.services.audit import record_audit
from app.services.errors import ValidationFailed
from app.timeutil import utc_now


def list_inventory(
    db: Session,
    search: str | None = None,
    spare_type: str | None = None,
    in_stock_only: bool = False,
) -> list[InventoryItem]:
    """List inventory items with search and category filters."""
    query = db.query(InventoryItem).filter(InventoryItem.is_deleted.is_(False))

    if spare_type and spare_type.strip() and spare_type.strip().lower() != "all":
        query = query.filter(InventoryItem.spare_type == spare_type.strip().lower())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                InventoryItem.model.ilike(term),
                InventoryItem.supplier_name.ilike(term),
                InventoryItem.notes.ilike(term),
                InventoryItem.spare_type.ilike(term),
            )
        )

    if in_stock_only:
        query = query.filter(InventoryItem.quantity > 0)

    return query.order_by(InventoryItem.spare_type.asc(), InventoryItem.model.asc()).all()


def get_inventory_item(db: Session, item_id: int) -> InventoryItem | None:
    """Retrieve an active inventory item by id."""
    return db.query(InventoryItem).filter_by(id=item_id, is_deleted=False).first()


def get_available_spares(db: Session, model: str | None = None) -> list[InventoryItem]:
    """Retrieve spares that are currently in stock (quantity > 0)."""
    query = db.query(InventoryItem).filter(
        InventoryItem.is_deleted.is_(False),
        InventoryItem.quantity > 0,
    )
    if model and model.strip():
        term = f"%{model.strip()}%"
        query = query.filter(InventoryItem.model.ilike(term))
    return query.order_by(InventoryItem.spare_type.asc(), InventoryItem.model.asc()).all()


def add_inventory_item(
    db: Session,
    spare_type: str,
    model: str,
    quantity: int = 1,
    cost_price: int = 0,
    selling_price: int = 0,
    supplier_name: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> InventoryItem:
    """Add a new spare part to inventory."""
    current_time = now or utc_now()
    st = spare_type.strip().lower()
    md = model.strip()

    if not st:
        raise ValidationFailed("Spare type/category is required")
    if not md or len(md) > 100:
        raise ValidationFailed("Device model must be between 1 and 100 characters")
    if quantity < 0:
        raise ValidationFailed("Quantity cannot be negative")
    if cost_price < 0 or cost_price > 10_00_000:
        raise ValidationFailed("Cost price must be between 0 and ₹10,00,000")
    if selling_price < 0 or selling_price > 10_00_000:
        raise ValidationFailed("Selling price must be between 0 and ₹10,00,000")

    item = InventoryItem(
        spare_type=st,
        model=md,
        quantity=quantity,
        cost_price=cost_price,
        selling_price=selling_price,
        supplier_name=supplier_name.strip() if supplier_name else None,
        notes=notes.strip() if notes else None,
        is_deleted=False,
    )
    db.add(item)
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.INVENTORY.value,
        entity_id=item.id,
        action=AuditAction.CREATE.value,
        changed_fields={
            "spare_type": {"old": None, "new": st},
            "model": {"old": None, "new": md},
            "quantity": {"old": None, "new": quantity},
            "cost_price": {"old": None, "new": cost_price},
            "selling_price": {"old": None, "new": selling_price},
            "supplier_name": {"old": None, "new": item.supplier_name},
        },
        now=current_time,
    )

    return item


def edit_inventory_item(
    db: Session,
    item: InventoryItem,
    spare_type: str,
    model: str,
    quantity: int,
    cost_price: int = 0,
    selling_price: int = 0,
    supplier_name: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> InventoryItem:
    """Update inventory item details and log changes."""
    current_time = now or utc_now()
    st = spare_type.strip().lower()
    md = model.strip()

    if not st:
        raise ValidationFailed("Spare type/category is required")
    if not md or len(md) > 100:
        raise ValidationFailed("Device model must be between 1 and 100 characters")
    if quantity < 0:
        raise ValidationFailed("Quantity cannot be negative")
    if cost_price < 0 or cost_price > 10_00_000:
        raise ValidationFailed("Cost price must be between 0 and ₹10,00,000")
    if selling_price < 0 or selling_price > 10_00_000:
        raise ValidationFailed("Selling price must be between 0 and ₹10,00,000")

    supp = supplier_name.strip() if supplier_name else None
    nt = notes.strip() if notes else None

    changes: dict[str, Any] = {}
    if item.spare_type != st:
        changes["spare_type"] = {"old": item.spare_type, "new": st}
        item.spare_type = st
    if item.model != md:
        changes["model"] = {"old": item.model, "new": md}
        item.model = md
    if item.quantity != quantity:
        changes["quantity"] = {"old": item.quantity, "new": quantity}
        item.quantity = quantity
    if item.cost_price != cost_price:
        changes["cost_price"] = {"old": item.cost_price, "new": cost_price}
        item.cost_price = cost_price
    if item.selling_price != selling_price:
        changes["selling_price"] = {"old": item.selling_price, "new": selling_price}
        item.selling_price = selling_price
    if item.supplier_name != supp:
        changes["supplier_name"] = {"old": item.supplier_name, "new": supp}
        item.supplier_name = supp
    if item.notes != nt:
        changes["notes"] = {"old": item.notes, "new": nt}
        item.notes = nt

    if changes:
        item.updated_at = current_time
        db.flush()
        record_audit(
            db=db,
            entity=AuditEntity.INVENTORY.value,
            entity_id=item.id,
            action=AuditAction.UPDATE.value,
            changed_fields=changes,
            now=current_time,
        )

    return item


def adjust_inventory_stock(
    db: Session,
    item: InventoryItem | int,
    delta: int,
    reason: str | None = None,
    now: datetime | None = None,
) -> InventoryItem:
    """Increment or decrement item stock quantity."""
    if isinstance(item, int):
        fetched = get_inventory_item(db, item)
        if not fetched:
            raise ValidationFailed("Inventory item not found")
        item = fetched

    current_time = now or utc_now()
    new_qty = item.quantity + delta
    if new_qty < 0:
        raise ValidationFailed(f"Insufficient stock for {item.spare_type.title()} ({item.model}). Available: {item.quantity}")

    old_qty = item.quantity
    item.quantity = new_qty
    item.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.INVENTORY.value,
        entity_id=item.id,
        action=AuditAction.UPDATE.value,
        changed_fields={"quantity": {"old": old_qty, "new": new_qty}},
        reason=reason,
        now=current_time,
    )

    return item


def delete_inventory_item(
    db: Session,
    item: InventoryItem | int,
    now: datetime | None = None,
) -> InventoryItem:
    """Soft delete an inventory item."""
    if isinstance(item, int):
        fetched = get_inventory_item(db, item)
        if not fetched:
            raise ValidationFailed("Inventory item not found")
        item = fetched

    current_time = now or utc_now()
    item.is_deleted = True
    item.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.INVENTORY.value,
        entity_id=item.id,
        action=AuditAction.DELETE.value,
        now=current_time,
    )

    return item
