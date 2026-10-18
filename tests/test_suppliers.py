import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import get_db
from app.main import app
from app.models.enums import SpareCategory
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret
from app.services.errors import ValidationFailed
from app.services.inventory import add_inventory_item
from app.services.items import add_item, delete_item
from app.services.suppliers import (
    create_supplier,
    delete_supplier,
    delete_supplier_payment,
    get_all_suppliers_summary,
    get_supplier_by_name,
    get_supplier_ledger,
    list_suppliers,
    record_supplier_payment,
    update_supplier,
)
from app.services.tickets import create_ticket


@pytest.fixture
def client(temp_db):
    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, follow_redirects=False) as c:
        s = temp_db.query(SettingsModel).filter_by(id=1).first()
        s.owner_pin_hash = hash_secret("1234")
        s.admin_password_hash = hash_secret("admin123")
        s.setup_completed = True
        temp_db.commit()

        login_res = c.post(
            "/login",
            data={"password": "admin123"},
        )
        assert login_res.status_code == 303
        yield c

    app.dependency_overrides.clear()


def test_supplier_crud_and_anti_delete(temp_db):
    # 1. Create supplier
    sup = create_supplier(
        db=temp_db,
        name="Global Displays",
        phone="9876543210",
        email="global@displays.com",
        contact_person="Ramesh",
        address="Shop 12, Electronics Market",
        notes="Fast delivery for OLED screens",
    )
    temp_db.commit()

    assert sup.id is not None
    assert sup.name == "Global Displays"
    assert sup.phone == "9876543210"
    assert not sup.is_deleted

    # Duplicate name should raise ValidationFailed
    with pytest.raises(ValidationFailed, match="already exists"):
        create_supplier(db=temp_db, name="Global Displays")

    # Name is case-insensitively trimmed
    with pytest.raises(ValidationFailed, match="already exists"):
        create_supplier(db=temp_db, name="  global displays  ")

    # 2. Update supplier
    updated = update_supplier(
        db=temp_db,
        supplier=sup,
        phone="9998887776",
        notes="Updated notes",
    )
    temp_db.commit()
    assert updated.phone == "9998887776"
    assert updated.notes == "Updated notes"

    # 3. Soft delete supplier
    delete_supplier(db=temp_db, supplier=sup)
    temp_db.commit()
    assert sup.is_deleted is True

    # Active list should not include deleted
    active = list_suppliers(temp_db, active_only=True)
    assert sup.id not in [s.id for s in active]

    all_sups = list_suppliers(temp_db, active_only=False)
    assert sup.id in [s.id for s in all_sups]

    # 4. Anti-delete trigger should prevent hard deletion
    with pytest.raises(DBAPIError, match="Hard delete is forbidden on suppliers"):
        temp_db.execute(text("DELETE FROM suppliers WHERE id = :id"), {"id": sup.id})
        temp_db.commit()
    temp_db.rollback()


def test_supplier_payments_and_ledger(temp_db):
    # Setup supplier
    sup = create_supplier(
        db=temp_db,
        name="Star Spares",
        phone="9811122233",
    )
    temp_db.commit()

    # Create ticket
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9870001111",
        customer_name="John Doe",
        device_brand="Samsung",
        device_model="Galaxy S21",
        reported_issue="Cracked display and dead battery",
    )
    temp_db.commit()

    # Add labor (should NOT count towards supplier purchase)
    add_item(
        db=temp_db,
        ticket=ticket,
        item_type="labor",
        description="Screen fitting fee",
        price_charged=500,
    )

    # Add part with supplier_id (cost 3200, price 4500)
    item1 = add_item(
        db=temp_db,
        ticket=ticket,
        item_type="part",
        description="S21 Dynamic AMOLED Display",
        price_charged=4500,
        cost_price=3200,
        supplier_id=sup.id,
    )
    temp_db.commit()

    # Add part without supplier_id but with matching supplier_name
    item2 = add_item(
        db=temp_db,
        ticket=ticket,
        item_type="part",
        description="S21 Battery OEM",
        price_charged=1800,
        cost_price=900,
        supplier_name="star spares",  # should auto-link
    )
    temp_db.commit()
    assert item2.supplier_id == sup.id

    # Check ledger before payments
    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger is not None
    assert ledger["total_parts_bought"] == 4100  # 3200 + 900
    assert ledger["total_paid"] == 0
    assert ledger["pending_payment"] == 4100
    assert len(ledger["ticket_parts"]) == 2

    # Make partial payment: 2500 via UPI
    pay1 = record_supplier_payment(
        db=temp_db,
        supplier_id=sup.id,
        amount=2500,
        mode="upi",
        reference="UPI987654321",
        notes="Part payment for S21 screen",
    )
    temp_db.commit()

    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_parts_bought"] == 4100
    assert ledger["total_paid"] == 2500
    assert ledger["pending_payment"] == 1600
    assert len(ledger["payments"]) == 1

    # Make final payment: 1600 via cash
    pay2 = record_supplier_payment(
        db=temp_db,
        supplier_id=sup.id,
        amount=1600,
        mode="cash",
        reference="CASH-REC-1",
        notes="Cleared remaining balance",
    )
    temp_db.commit()

    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_parts_bought"] == 4100
    assert ledger["total_paid"] == 4100
    assert ledger["pending_payment"] == 0
    assert len(ledger["payments"]) == 2

    # Soft delete a payment
    delete_supplier_payment(temp_db, pay2, reason="Duplicate entry")
    temp_db.commit()

    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_paid"] == 2500
    assert ledger["pending_payment"] == 1600

    # Hard delete payment should fail trigger
    with pytest.raises(DBAPIError, match="Hard delete is forbidden on supplier_payments"):
        temp_db.execute(text("DELETE FROM supplier_payments WHERE id = :id"), {"id": pay1.id})
        temp_db.commit()
    temp_db.rollback()

    # Soft deleting a ticket item excludes it from ledger
    delete_item(temp_db, item1)
    temp_db.commit()

    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_parts_bought"] == 900  # only item2 remains
    assert ledger["total_paid"] == 2500
    assert ledger["pending_payment"] == -1600  # overpaid


def test_supplier_inventory_catalog_and_summary(temp_db):
    sup1 = create_supplier(temp_db, name="Vendor A")
    create_supplier(temp_db, name="Vendor B")
    temp_db.commit()

    # Add inventory item linked to sup1
    inv1 = add_inventory_item(
        db=temp_db,
        spare_type=SpareCategory.BATTERY.value,
        model="OnePlus 9 Battery",
        quantity=4,
        cost_price=800,
        selling_price=1500,
        supplier_id=sup1.id,
    )
    temp_db.commit()

    ledger1 = get_supplier_ledger(temp_db, sup1.id)
    assert len(ledger1["inventory_items"]) == 1
    assert ledger1["inventory_items"][0].id == inv1.id

    # Check overall summary
    summary = get_all_suppliers_summary(temp_db)
    assert summary["total_suppliers"] >= 2


def _extract_csrf(res):
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res.text)
    return m.group(1) if m else ""


def test_supplier_web_routes(client, temp_db):
    # 1. GET /suppliers
    res = client.get("/suppliers")
    assert res.status_code == 200
    assert "Suppliers" in res.text
    token = _extract_csrf(res)

    # 2. POST /suppliers (create)
    res = client.post(
        "/suppliers",
        data={
            "csrf_token": token,
            "name": "Prime Mobile Parts",
            "phone": "9988776655",
            "email": "prime@parts.com",
            "contact_person": "Vikram",
            "address": "Bangalore SP Road",
            "notes": "Main screen vendor",
        },
    )
    assert res.status_code == 303
    sup = get_supplier_by_name(temp_db, "Prime Mobile Parts")
    assert sup is not None

    # 3. GET /suppliers/{id}
    res = client.get(f"/suppliers/{sup.id}")
    assert res.status_code == 200
    assert "Prime Mobile Parts" in res.text
    assert "Supplier Ledger" in res.text
    token = _extract_csrf(res)

    # 4. POST /suppliers/{id}/payments
    res = client.post(
        f"/suppliers/{sup.id}/payments",
        data={
            "csrf_token": token,
            "amount": "5000",
            "mode": "bank_transfer",
            "reference": "NEFT123456",
            "notes": "Advance deposit",
        },
    )
    assert res.status_code == 303

    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_paid"] == 5000

    # 5. POST /suppliers/{id}/edit
    res = client.post(
        f"/suppliers/{sup.id}/edit",
        data={
            "csrf_token": token,
            "name": "Prime Mobile Parts Pvt Ltd",
            "phone": "9988776655",
            "email": "contact@primeparts.com",
            "contact_person": "Vikram S",
            "address": "Bangalore SP Road",
            "notes": "Updated notes",
        },
    )
    assert res.status_code == 303
    temp_db.refresh(sup)
    assert sup.name == "Prime Mobile Parts Pvt Ltd"

    # 6. POST /suppliers/{id}/delete
    res = client.post(
        f"/suppliers/{sup.id}/delete",
        data={"csrf_token": token},
    )
    assert res.status_code == 303
    temp_db.refresh(sup)
    assert sup.is_deleted is True


def test_ticket_line_item_with_supplier_dropdown(client, temp_db):
    # Setup registered supplier
    sup = create_supplier(temp_db, name="QuickFix Spares", phone="9123456789")
    temp_db.commit()

    # Create ticket
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9876500000",
        customer_name="Alice Smith",
        device_brand="Apple",
        device_model="iPhone 12",
        reported_issue="Broken back glass",
    )
    temp_db.commit()

    # Open ticket detail page - verify supplier options are present
    res = client.get(f"/tickets/{ticket.id}")
    assert res.status_code == 200
    assert "QuickFix Spares" in res.text
    assert "item_supplier_select" in res.text
    token = _extract_csrf(res)

    # Add line item with supplier_id selected
    res = client.post(
        f"/tickets/{ticket.id}/items",
        data={
            "csrf_token": token,
            "item_type": "part",
            "description": "iPhone 12 OEM Back Glass",
            "price_charged": "1800",
            "cost_price": "750",
            "supplier_id": str(sup.id),
        },
    )
    assert res.status_code == 303

    # Verify item was created with supplier linked
    temp_db.refresh(ticket)
    part_item = next(i for i in ticket.items if not i.is_deleted and i.type == "part")
    assert part_item.supplier_id == sup.id
    assert part_item.supplier_name == "QuickFix Spares"
    assert part_item.cost_price == 750

    # Verify supplier ledger reflects this part and cost price
    ledger = get_supplier_ledger(temp_db, sup.id)
    assert ledger["total_parts_bought"] == 750
    assert ledger["pending_payment"] == 750
    assert len(ledger["ticket_parts"]) == 1
    assert ledger["ticket_parts"][0]["description"] == "iPhone 12 OEM Back Glass"
    assert ledger["ticket_parts"][0]["cost_price"] == 750
