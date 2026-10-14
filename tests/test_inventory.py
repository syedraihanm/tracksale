import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.enums import SpareCategory
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret
from app.services.errors import ValidationFailed
from app.services.inventory import (
    add_inventory_item,
    adjust_inventory_stock,
    delete_inventory_item,
    edit_inventory_item,
    get_available_spares,
    get_inventory_item,
    list_inventory,
)
from app.services.items import add_item, delete_item
from app.services.tickets import create_ticket


@pytest.fixture
def client(temp_db):
    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Setup session user
    with TestClient(app, follow_redirects=False) as c:
        # Log in as owner/admin
        s = temp_db.query(SettingsModel).filter_by(id=1).first()
        s.owner_pin_hash = hash_secret("1234")
        s.admin_password_hash = hash_secret("admin123")
        s.setup_completed = True
        temp_db.commit()

        # Seed session cookie
        login_res = c.post(
            "/login",
            data={"password": "admin123"},
        )
        assert login_res.status_code == 303
        yield c

    app.dependency_overrides.clear()


def test_inventory_service_crud(temp_db):
    # Add display spare
    item = add_inventory_item(
        db=temp_db,
        spare_type=SpareCategory.DISPLAY.value,
        model="iPhone 13 Pro OLED",
        quantity=5,
        cost_price=3500,
        selling_price=5500,
        supplier_name="Metro Spares",
        notes="Grade A OEM display",
    )
    assert item.id is not None
    assert item.spare_type == "display"
    assert item.quantity == 5

    # Add battery spare
    add_inventory_item(
        db=temp_db,
        spare_type=SpareCategory.BATTERY.value,
        model="Samsung S21",
        quantity=2,
        cost_price=900,
        selling_price=1600,
        supplier_name="FastCell",
    )

    # List inventory
    items = list_inventory(temp_db)
    assert len(items) == 2

    # Filter by category
    displays = list_inventory(temp_db, spare_type="display")
    assert len(displays) == 1
    assert displays[0].model == "iPhone 13 Pro OLED"

    # Search
    searched = list_inventory(temp_db, search="Samsung")
    assert len(searched) == 1
    assert searched[0].spare_type == "battery"

    # Edit item
    updated = edit_inventory_item(
        db=temp_db,
        item=item,
        spare_type="display",
        model="iPhone 13 Pro MAX OLED",
        quantity=4,
        cost_price=3600,
        selling_price=5800,
        supplier_name="Metro Spares Hub",
        notes="Updated batch",
    )
    assert updated.model == "iPhone 13 Pro MAX OLED"
    assert updated.quantity == 4
    assert updated.cost_price == 3600

    # Stock adjustment
    adjust_inventory_stock(temp_db, item.id, delta=2)
    reloaded = get_inventory_item(temp_db, item.id)
    assert reloaded.quantity == 6

    adjust_inventory_stock(temp_db, item.id, delta=-1)
    reloaded = get_inventory_item(temp_db, item.id)
    assert reloaded.quantity == 5

    # Cannot adjust below zero
    with pytest.raises(ValidationFailed):
        adjust_inventory_stock(temp_db, item.id, delta=-10)

    # Delete item
    delete_inventory_item(temp_db, item.id)
    assert get_inventory_item(temp_db, item.id) is None
    assert len(list_inventory(temp_db)) == 1


def test_inventory_ticket_item_integration(temp_db):
    # Setup owner PIN
    s = temp_db.query(SettingsModel).filter_by(id=1).first()
    s.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    # Create ticket
    t = create_ticket(
        db=temp_db,
        customer_phone="9876543210",
        customer_name="Rohan Sharma",
        device_brand="Apple",
        device_model="iPhone 12",
        reported_issue="Cracked Screen",
    )

    # Add spare item in inventory
    inv = add_inventory_item(
        db=temp_db,
        spare_type="display",
        model="iPhone 12 Original",
        quantity=3,
        cost_price=2800,
        selling_price=4200,
        supplier_name="Apple Spares Hub",
    )

    # Add repair line item linked to inventory
    line_item = add_item(
        db=temp_db,
        ticket=t,
        item_type="part",
        description="Display - iPhone 12 Original",
        price_charged=4200,
        cost_price=2800,
        supplier_name="Apple Spares Hub",
        inventory_item_id=inv.id,
    )

    assert line_item.inventory_item_id == inv.id

    # Stock should be decremented from 3 to 2
    temp_db.refresh(inv)
    assert inv.quantity == 2

    # Delete line item -> stock should replenish back to 3
    delete_item(db=temp_db, item=line_item)
    temp_db.refresh(inv)
    assert inv.quantity == 3


def test_out_of_stock_inventory_item(temp_db):
    t = create_ticket(
        db=temp_db,
        customer_phone="9876543210",
        customer_name="Rohan Sharma",
        device_brand="OnePlus",
        device_model="Nord CE",
        reported_issue="Battery Draining",
    )

    inv = add_inventory_item(
        db=temp_db,
        spare_type="battery",
        model="Nord CE 4500mAh",
        quantity=0,
        cost_price=700,
        selling_price=1200,
    )

    # Should not be returned in get_available_spares
    available = get_available_spares(temp_db)
    assert all(item.id != inv.id for item in available)

    # Adding item linked to out-of-stock spare raises error
    with pytest.raises(ValidationFailed, match="out of stock"):
        add_item(
            db=temp_db,
            ticket=t,
            item_type="part",
            description="Battery replacement",
            price_charged=1200,
            inventory_item_id=inv.id,
        )


def test_inventory_web_routes(client, temp_db):
    # GET /inventory
    resp = client.get("/inventory")
    assert resp.status_code == 200
    assert "Spares Inventory" in resp.text

    # Extract CSRF token from page
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
    csrf_token = m.group(1) if m else ""

    # POST /inventory (add spare)
    post_resp = client.post(
        "/inventory",
        data={
            "csrf_token": csrf_token,
            "spare_type": "motherboard",
            "model": "Redmi Note 10 Pro Motherboard",
            "quantity": 2,
            "cost_price": "2500",
            "selling_price": "4000",
            "supplier_name": "MI Authorized Hub",
            "notes": "Tested working 100%",
        },
    )
    assert post_resp.status_code == 303
    assert post_resp.headers["location"] == "/inventory"

    # Verify created
    items = list_inventory(temp_db)
    assert len(items) == 1
    spare = items[0]
    assert spare.spare_type == "motherboard"
    assert spare.quantity == 2

    # POST /inventory/{id}/stock (+1)
    stock_resp = client.post(
        f"/inventory/{spare.id}/stock",
        data={
            "csrf_token": csrf_token,
            "delta": 1,
        },
    )
    assert stock_resp.status_code == 303
    temp_db.refresh(spare)
    assert spare.quantity == 3


def test_inventory_audit_and_trigger_protection(temp_db):
    from sqlalchemy import text

    from app.models.audit_log import AuditLog

    # Create inventory item with quantity 3
    inv = add_inventory_item(
        db=temp_db,
        spare_type="display",
        model="Galaxy S20",
        quantity=3,
        cost_price=1500,
        selling_price=2500,
    )
    assert inv.quantity == 3

    t = create_ticket(
        db=temp_db,
        customer_phone="9988776655",
        customer_name="Pooja Patel",
        device_brand="Samsung",
        device_model="Galaxy S20",
        reported_issue="Blank Screen",
    )

    # Attach it as a part line item -> quantity becomes 2
    item = add_item(
        db=temp_db,
        ticket=t,
        item_type="part",
        description="Display Replacement",
        price_charged=2500,
        inventory_item_id=inv.id,
    )
    temp_db.refresh(inv)
    assert inv.quantity == 2

    # Soft-delete line item -> quantity becomes 3 and audit_log recorded
    delete_item(db=temp_db, item=item)
    temp_db.refresh(inv)
    assert inv.quantity == 3

    # Check audit log contains record for inventory stock adjustment
    audits = (
        temp_db.query(AuditLog)
        .filter(AuditLog.entity == "inventory", AuditLog.entity_id == inv.id)
        .all()
    )
    assert len(audits) >= 2  # create + adjust
    actions = [a.action for a in audits]
    assert "create" in actions
    assert "update" in actions

    # Attempt to hard-delete inventory item via raw SQL -> trigger must abort
    with pytest.raises(Exception, match="Hard delete is forbidden on inventory_items"):
        temp_db.execute(text("DELETE FROM inventory_items WHERE id = :id"), {"id": inv.id})
        temp_db.commit()
    temp_db.rollback()

