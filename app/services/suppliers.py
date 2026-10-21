from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.enums import AuditAction, AuditEntity
from app.models.inventory import InventoryItem
from app.models.supplier import Supplier, SupplierPayment
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.services.audit import record_audit
from app.services.errors import ValidationFailed
from app.timeutil import utc_now


def list_suppliers(
    db: Session,
    search: str | None = None,
    active_only: bool = True,
) -> list[Supplier]:
    """List suppliers with optional search and active filtering."""
    query = db.query(Supplier)
    if active_only:
        query = query.filter(Supplier.is_deleted.is_(False))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Supplier.name.ilike(term),
                Supplier.phone.ilike(term),
                Supplier.contact_person.ilike(term),
                Supplier.notes.ilike(term),
            )
        )

    return query.order_by(Supplier.name.asc()).all()


def get_supplier(db: Session, supplier_id: int) -> Supplier | None:
    """Get supplier by ID."""
    return db.query(Supplier).filter_by(id=supplier_id, is_deleted=False).first()


def get_supplier_by_name(db: Session, name: str) -> Supplier | None:
    """Get active supplier by name (case-insensitive)."""
    if not name or not name.strip():
        return None
    return (
        db.query(Supplier)
        .filter(
            func.lower(Supplier.name) == func.lower(name.strip()),
            Supplier.is_deleted.is_(False),
        )
        .first()
    )


def create_supplier(
    db: Session,
    name: str,
    phone: str | None = None,
    email: str | None = None,
    contact_person: str | None = None,
    address: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> Supplier:
    """Create a new supplier with duplicate name check and audit logging."""
    current_time = now or utc_now()
    clean_name = name.strip() if name else ""

    if not clean_name or len(clean_name) > 100:
        raise ValidationFailed("Supplier name must be between 1 and 100 characters")

    # Check for existing supplier with the same name
    existing = (
        db.query(Supplier)
        .filter(func.lower(Supplier.name) == func.lower(clean_name))
        .first()
    )
    if existing:
        if existing.is_deleted:
            # Reactivate soft-deleted supplier
            existing.is_deleted = False
            existing.phone = phone.strip() if phone else None
            existing.email = email.strip() if email else None
            existing.contact_person = contact_person.strip() if contact_person else None
            existing.address = address.strip() if address else None
            existing.notes = notes.strip() if notes else None
            existing.updated_at = current_time
            db.flush()
            record_audit(
                db=db,
                entity=AuditEntity.SUPPLIER.value,
                entity_id=existing.id,
                action=AuditAction.UPDATE.value,
                changed_fields={"is_deleted": {"old": True, "new": False}},
                reason="Reactivated soft-deleted supplier",
                now=current_time,
            )
            return existing
        else:
            raise ValidationFailed(f"Supplier '{clean_name}' already exists")

    supplier = Supplier(
        name=clean_name,
        phone=phone.strip() if phone else None,
        email=email.strip() if email else None,
        contact_person=contact_person.strip() if contact_person else None,
        address=address.strip() if address else None,
        notes=notes.strip() if notes else None,
        is_deleted=False,
    )
    db.add(supplier)
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.SUPPLIER.value,
        entity_id=supplier.id,
        action=AuditAction.CREATE.value,
        changed_fields={
            "name": {"old": None, "new": clean_name},
            "phone": {"old": None, "new": supplier.phone},
            "contact_person": {"old": None, "new": supplier.contact_person},
        },
        now=current_time,
    )

    return supplier


def update_supplier(
    db: Session,
    supplier: Supplier | int,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    contact_person: str | None = None,
    address: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> Supplier:
    """Update supplier details and log changes."""
    current_time = now or utc_now()
    if isinstance(supplier, int):
        sup = get_supplier(db, supplier)
        if not sup:
            raise ValidationFailed("Supplier not found")
        supplier = sup

    changes: dict[str, Any] = {}
    if name is not None:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 100:
            raise ValidationFailed("Supplier name must be between 1 and 100 characters")

        # Check for name collision with another supplier
        existing = (
            db.query(Supplier)
            .filter(
                func.lower(Supplier.name) == func.lower(clean_name),
                Supplier.id != supplier.id,
                Supplier.is_deleted.is_(False),
            )
            .first()
        )
        if existing:
            raise ValidationFailed(f"Another supplier named '{clean_name}' already exists")

        if supplier.name != clean_name:
            changes["name"] = {"old": supplier.name, "new": clean_name}
            supplier.name = clean_name

    clean_phone = phone.strip() if phone else None
    clean_email = email.strip() if email else None
    clean_contact = contact_person.strip() if contact_person else None
    clean_address = address.strip() if address else None
    clean_notes = notes.strip() if notes else None

    if phone is not None and supplier.phone != clean_phone:
        changes["phone"] = {"old": supplier.phone, "new": clean_phone}
        supplier.phone = clean_phone
    if email is not None and supplier.email != clean_email:
        changes["email"] = {"old": supplier.email, "new": clean_email}
        supplier.email = clean_email
    if contact_person is not None and supplier.contact_person != clean_contact:
        changes["contact_person"] = {"old": supplier.contact_person, "new": clean_contact}
        supplier.contact_person = clean_contact
    if address is not None and supplier.address != clean_address:
        changes["address"] = {"old": supplier.address, "new": clean_address}
        supplier.address = clean_address
    if notes is not None and supplier.notes != clean_notes:
        changes["notes"] = {"old": supplier.notes, "new": clean_notes}
        supplier.notes = clean_notes

    if changes:
        supplier.updated_at = current_time
        db.flush()
        record_audit(
            db=db,
            entity=AuditEntity.SUPPLIER.value,
            entity_id=supplier.id,
            action=AuditAction.UPDATE.value,
            changed_fields=changes,
            now=current_time,
        )

    return supplier


def delete_supplier(
    db: Session,
    supplier: Supplier | int,
    now: datetime | None = None,
) -> Supplier:
    """Soft delete a supplier."""
    current_time = now or utc_now()
    if isinstance(supplier, int):
        sup = get_supplier(db, supplier)
        if not sup:
            raise ValidationFailed("Supplier not found")
        supplier = sup

    supplier.is_deleted = True
    supplier.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.SUPPLIER.value,
        entity_id=supplier.id,
        action=AuditAction.DELETE.value,
        now=current_time,
    )

    return supplier


def record_supplier_payment(
    db: Session,
    supplier: Supplier | int | None = None,
    amount: int = 0,
    mode: str = "cash",
    reference: str | None = None,
    notes: str | None = None,
    paid_at: datetime | None = None,
    now: datetime | None = None,
    *,
    supplier_id: int | None = None,
) -> SupplierPayment:
    """Record a payment made to a supplier."""
    current_time = now or utc_now()
    payment_time = paid_at or current_time

    target = supplier if supplier is not None else supplier_id
    if target is None:
        raise ValidationFailed("Supplier is required")

    if isinstance(target, int):
        sup = get_supplier(db, target)
        if not sup:
            raise ValidationFailed("Supplier not found")
        supplier = sup
    else:
        supplier = target

    if amount <= 0:
        raise ValidationFailed("Payment amount must be greater than ₹0")
    if amount > 10_000_000:
        raise ValidationFailed("Payment amount exceeds maximum limit (₹1 Crore)")

    clean_mode = mode.strip().lower() if mode else "cash"
    allowed_modes = {"cash", "upi", "bank_transfer", "card", "cheque"}
    if clean_mode not in allowed_modes:
        raise ValidationFailed(f"Invalid payment mode '{clean_mode}'. Allowed: {', '.join(allowed_modes)}")

    payment = SupplierPayment(
        supplier_id=supplier.id,
        amount=amount,
        mode=clean_mode,
        reference=reference.strip() if reference else None,
        notes=notes.strip() if notes else None,
        paid_at=payment_time,
        is_deleted=False,
    )
    db.add(payment)
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.SUPPLIER_PAYMENT.value,
        entity_id=payment.id,
        action=AuditAction.CREATE.value,
        changed_fields={
            "supplier_id": {"old": None, "new": supplier.id},
            "supplier_name": {"old": None, "new": supplier.name},
            "amount": {"old": None, "new": amount},
            "mode": {"old": None, "new": clean_mode},
            "reference": {"old": None, "new": payment.reference},
        },
        now=current_time,
    )

    return payment


def add_supplier_pending_balance(
    db: Session,
    supplier: Supplier | int,
    amount: int,
    notes: str | None = None,
    now: datetime | None = None,
) -> Supplier:
    """Add an amount directly to what is pending to a supplier."""
    current_time = now or utc_now()
    if isinstance(supplier, int):
        sup = get_supplier(db, supplier)
        if not sup:
            raise ValidationFailed("Supplier not found")
        supplier = sup

    if amount <= 0:
        raise ValidationFailed("Amount to add must be greater than ₹0")
    if amount > 100_000_000:
        raise ValidationFailed("Amount exceeds maximum limit (₹10 Crore)")

    previous_amount = supplier.pending_adjustment or 0
    supplier.pending_adjustment = previous_amount + amount
    supplier.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.SUPPLIER.value,
        entity_id=supplier.id,
        action=AuditAction.UPDATE.value,
        changed_fields={
            "pending_balance_added": {"old": previous_amount, "new": supplier.pending_adjustment},
            "amount_added": amount,
        },
        reason=notes.strip() if notes and notes.strip() else "Amount added to supplier pending balance",
        now=current_time,
    )
    return supplier


def delete_supplier_payment(
    db: Session,
    payment: SupplierPayment | int,
    reason: str | None = None,
    now: datetime | None = None,
) -> SupplierPayment:
    """Soft delete a supplier payment."""
    current_time = now or utc_now()
    if isinstance(payment, int):
        pmt = db.query(SupplierPayment).filter_by(id=payment, is_deleted=False).first()
        if not pmt:
            raise ValidationFailed("Supplier payment not found")
        payment = pmt

    payment.is_deleted = True
    payment.deleted_reason = reason.strip() if reason else "Voided payment"
    payment.deleted_at = current_time
    payment.updated_at = current_time
    db.flush()

    record_audit(
        db=db,
        entity=AuditEntity.SUPPLIER_PAYMENT.value,
        entity_id=payment.id,
        action=AuditAction.DELETE.value,
        reason=reason,
        now=current_time,
    )

    return payment


def get_supplier_ledger(db: Session, supplier_id: int) -> dict[str, Any]:
    """Retrieve full purchase history, payment history, and pending balance for a supplier."""
    supplier = db.query(Supplier).filter_by(id=supplier_id, is_deleted=False).first()
    if not supplier:
        raise ValidationFailed("Supplier not found")

    # 1. Fetch parts bought from this supplier (from TicketItem where type == 'part')
    # Match by supplier_id OR matching supplier_name (case-insensitive)
    items_query = (
        db.query(TicketItem, Ticket)
        .join(Ticket, TicketItem.ticket_id == Ticket.id)
        .filter(
            TicketItem.type == "part",
            TicketItem.is_deleted.is_(False),
            or_(
                TicketItem.supplier_id == supplier.id,
                func.lower(TicketItem.supplier_name) == func.lower(supplier.name),
            ),
        )
        .order_by(TicketItem.created_at.desc())
    )
    items_with_ticket = items_query.all()

    parts_purchased = []
    total_parts_cost = 0
    for item, ticket in items_with_ticket:
        total_parts_cost += item.cost_price
        parts_purchased.append({
            "item_id": item.id,
            "ticket_id": ticket.id,
            "ticket_no": ticket.ticket_no,
            "created_at": item.created_at,
            "description": item.description,
            "device_brand": ticket.device_brand,
            "device_model": ticket.device_model,
            "customer_name": ticket.customer.name if ticket.customer else "Walk-in",
            "cost_price": item.cost_price,
            "price_charged": item.price_charged,
            "ticket_status": ticket.status,
            "is_from_inventory": bool(item.inventory_item_id),
        })

    # 2. Fetch inventory catalog spares associated with this supplier
    inv_spares = (
        db.query(InventoryItem)
        .filter(
            InventoryItem.is_deleted.is_(False),
            or_(
                InventoryItem.supplier_id == supplier.id,
                func.lower(InventoryItem.supplier_name) == func.lower(supplier.name),
            ),
        )
        .order_by(InventoryItem.spare_type.asc(), InventoryItem.model.asc())
        .all()
    )

    total_inventory_stock_value = sum(s.cost_price * s.quantity for s in inv_spares)

    # 3. Fetch payments made to this supplier
    payments = (
        db.query(SupplierPayment)
        .filter_by(supplier_id=supplier.id, is_deleted=False)
        .order_by(SupplierPayment.paid_at.desc())
        .all()
    )
    total_paid = sum(p.amount for p in payments)

    # Total bought is total parts cost
    total_bought = total_parts_cost
    pending_adjustment = supplier.pending_adjustment or 0
    pending_payment = total_bought + pending_adjustment - total_paid

    return {
        "supplier": supplier,
        "parts_purchased": parts_purchased,
        "ticket_parts": parts_purchased,
        "inventory_spares": inv_spares,
        "inventory_items": inv_spares,
        "payments": payments,
        "total_parts_bought": total_parts_cost,
        "total_inventory_stock_value": total_inventory_stock_value,
        "total_bought": total_bought,
        "total_paid": total_paid,
        "pending_payment": pending_payment,
    }


def get_all_suppliers_summary(
    db: Session,
    search: str | None = None,
) -> dict[str, Any]:
    """Retrieve all suppliers with their total purchases, total paid, and pending balances."""
    suppliers = list_suppliers(db, search=search, active_only=True)

    summary_list = []
    total_bought_all = 0
    total_paid_all = 0
    total_pending_all = 0

    for sup in suppliers:
        # Sum parts cost
        # Match by supplier_id OR matching supplier_name (case-insensitive)
        parts_cost = (
            db.query(func.coalesce(func.sum(TicketItem.cost_price), 0))
            .filter(
                TicketItem.type == "part",
                TicketItem.is_deleted.is_(False),
                or_(
                    TicketItem.supplier_id == sup.id,
                    func.lower(TicketItem.supplier_name) == func.lower(sup.name),
                ),
            )
            .scalar()
            or 0
        )

        parts_count = (
            db.query(func.count(TicketItem.id))
            .filter(
                TicketItem.type == "part",
                TicketItem.is_deleted.is_(False),
                or_(
                    TicketItem.supplier_id == sup.id,
                    func.lower(TicketItem.supplier_name) == func.lower(sup.name),
                ),
            )
            .scalar()
            or 0
        )

        # Sum payments
        paid_amount = (
            db.query(func.coalesce(func.sum(SupplierPayment.amount), 0))
            .filter(
                SupplierPayment.supplier_id == sup.id,
                SupplierPayment.is_deleted.is_(False),
            )
            .scalar()
            or 0
        )

        payments_count = (
            db.query(func.count(SupplierPayment.id))
            .filter(
                SupplierPayment.supplier_id == sup.id,
                SupplierPayment.is_deleted.is_(False),
            )
            .scalar()
            or 0
        )

        pending_adjustment = sup.pending_adjustment or 0
        pending = parts_cost + pending_adjustment - paid_amount

        total_bought_all += parts_cost
        total_paid_all += paid_amount
        total_pending_all += pending

        summary_list.append({
            "supplier": sup,
            "total_bought": parts_cost,
            "total_paid": paid_amount,
            "pending_payment": pending,
            "parts_count": parts_count,
            "payments_count": payments_count,
        })

    return {
        "suppliers": summary_list,
        "total_suppliers": len(summary_list),
        "total_bought_all": total_bought_all,
        "total_paid_all": total_paid_all,
        "total_pending_all": total_pending_all,
    }
