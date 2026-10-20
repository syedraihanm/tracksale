from datetime import date

import pytest

from app.models.enums import PaymentKind, TicketStatus
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret, verify_secret
from app.services.customers import get_customer_summary, update_customer_notes
from app.services.errors import PinRequired, ValidationFailed
from app.services.items import add_item, delete_item, edit_item
from app.services.payments import add_payment
from app.services.receipts import generate_qr_svg, generate_whatsapp_url
from app.services.settings_service import (
    change_owner_pin,
    change_password,
    get_settings_model,
    update_receipt_and_templates,
    update_shop_details,
)
from app.services.status import transition_ticket
from app.services.tickets import (
    create_ticket,
    get_or_create_customer,
    update_ticket_details,
)
from app.services.warranty import create_warranty_return, is_under_warranty


def test_receipts_qr_and_whatsapp(temp_db):
    """Test inline QR SVG generation and WhatsApp wa.me link generation."""
    svg = generate_qr_svg("http://localhost:8000/t/R-1001")
    assert "<svg" in svg
    assert "</svg>" in svg

    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820012345",
        customer_name="Rohan",
        device_brand="Apple",
        device_model="iPhone 13",
        reported_issue="Screen broken",
    )
    temp_db.commit()

    wa_url = generate_whatsapp_url(
        ticket=ticket,
        template_text="Hello {name}, your device {device} ticket {ticket_no} is ready.",
        shop_name="Repair Pro",
    )
    assert "https://wa.me/919820012345" in wa_url
    assert "Rohan" in wa_url
    assert "iPhone" in wa_url


def test_warranty_status_and_return_ticket(temp_db):
    """Test warranty status computation and warranty return ticket linking."""
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820099887",
        customer_name="Warranty User",
        device_brand="Samsung",
        device_model="S22",
        reported_issue="Original repair",
    )
    add_item(temp_db, ticket, item_type="labor", description="Repair labor", price_charged=1000)
    add_payment(temp_db, ticket, amount=1000, mode="cash", kind=PaymentKind.FINAL.value)
    transition_ticket(temp_db, ticket, TicketStatus.IN_PROGRESS.value)
    transition_ticket(temp_db, ticket, TicketStatus.READY_FOR_PICKUP.value)
    transition_ticket(temp_db, ticket, TicketStatus.DELIVERED.value)
    temp_db.commit()

    assert is_under_warranty(ticket) is True

    # Create warranty return
    ret_ticket = create_warranty_return(
        db=temp_db,
        parent_ticket=ticket,
        reported_issue="Touch issue returned under warranty",
    )
    temp_db.commit()

    assert ret_ticket.parent_ticket_id == ticket.id
    assert ret_ticket.customer_id == ticket.customer_id
    assert ret_ticket.device_model == ticket.device_model


def test_customer_service_and_history(temp_db):
    """Test customer upsert, note updating, and ticket history lookup."""
    cust, created = get_or_create_customer(temp_db, "9820088776", "Customer History")
    assert created is True

    update_customer_notes(temp_db, cust, "VIP regular client")
    temp_db.commit()
    assert cust.notes == "VIP regular client"

    # Create ticket for customer
    t = create_ticket(
        db=temp_db,
        customer_phone=cust.phone,
        customer_name=cust.name,
        device_brand="Apple",
        device_model="iPad",
        reported_issue="Battery replacement",
    )
    temp_db.commit()

    summary = get_customer_summary(temp_db, cust.id)
    assert summary is not None
    assert len(summary["tickets"]) == 1
    assert summary["tickets"][0]["ticket"].ticket_no == t.ticket_no


def test_settings_service_updates_and_security(temp_db):
    """Test shop settings updating, password change, and owner PIN change."""
    settings = get_settings_model(temp_db)
    assert settings.shop_name is not None

    update_shop_details(
        db=temp_db,
        shop_name="City Quick Fix",
        shop_phone="9876543210",
        shop_address="Shop 4, Station Road",
        default_warranty_days=45,
        ticket_no_prefix="R",
    )
    update_receipt_and_templates(
        db=temp_db,
        receipt_terms_text="Updated terms",
        msg_template_intake="Welcome {ticket_no}",
        msg_template_ready="Ready {ticket_no}",
    )
    temp_db.commit()
    assert settings.shop_name == "City Quick Fix"
    assert settings.default_warranty_days == 45

    # Set initial owner pin and admin password
    settings.owner_pin_hash = hash_secret("1234")
    settings.admin_password_hash = hash_secret("oldpass123")
    temp_db.commit()

    # Change PIN with wrong current PIN
    with pytest.raises(PinRequired):
        change_owner_pin(temp_db, current_pin="wrong", new_pin="5678")

    # Change PIN with valid current PIN
    change_owner_pin(temp_db, current_pin="1234", new_pin="5678")
    temp_db.commit()

    # Changing the Shop PIN accepts either former credential, and updates both.
    with pytest.raises(ValidationFailed):
        change_password(temp_db, current_password="wrong", new_password="9876")

    change_password(temp_db, current_password="5678", new_password="9876")
    temp_db.commit()
    assert verify_secret(settings.admin_password_hash, "9876")
    assert verify_secret(settings.owner_pin_hash, "9876")


def test_item_delivered_pin_protection_and_delete(temp_db):
    """Test modifying/deleting items on a delivered ticket requires Owner PIN."""
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820077665",
        customer_name="Delivered Item Test",
        device_brand="OnePlus",
        device_model="10 Pro",
        reported_issue="Camera glass",
    )
    item = add_item(temp_db, ticket, item_type="labor", description="Glass fix", price_charged=500)
    add_payment(temp_db, ticket, amount=500, mode="cash", kind=PaymentKind.FINAL.value)
    transition_ticket(temp_db, ticket, TicketStatus.IN_PROGRESS.value)
    transition_ticket(temp_db, ticket, TicketStatus.READY_FOR_PICKUP.value)
    transition_ticket(temp_db, ticket, TicketStatus.DELIVERED.value)
    temp_db.commit()

    # Adding item on delivered ticket without PIN
    with pytest.raises(PinRequired):
        add_item(temp_db, ticket, item_type="labor", description="Extra cleaning", price_charged=100, owner_pin="wrong")

    # Adding item with valid PIN
    item2 = add_item(temp_db, ticket, item_type="labor", description="Extra cleaning", price_charged=100, owner_pin="1234")
    temp_db.commit()
    assert item2.price_charged == 100

    # Editing item on delivered ticket without PIN
    with pytest.raises(PinRequired):
        edit_item(temp_db, item, description="Glass fix + cleaning", price_charged=550, owner_pin="wrong")

    # Editing item with valid PIN
    edit_item(temp_db, item, description="Glass fix + cleaning", price_charged=550, owner_pin="1234")
    temp_db.commit()
    assert item.description == "Glass fix + cleaning"

    # Deleting item on delivered ticket without PIN
    with pytest.raises(PinRequired):
        delete_item(temp_db, item2, owner_pin="wrong")

    # Deleting item with valid PIN
    delete_item(temp_db, item2, owner_pin="1234")
    temp_db.commit()
    assert item2.is_deleted is True


def test_csv_importer(temp_db):
    """Test CSV import service dry-run and live import execution."""
    from app.services.importer import extract_rows_from_file, process_import

    csv_bytes = b"""Date,Customer Name,Phone,Brand,Model,Issue,Status,Charge,Payment Mode
2026-09-01,Ramesh Patel,9820011223,Samsung,Galaxy A51,Screen replacement,delivered,2500,cash
2026-09-02,Sita Verma,9820022334,Apple,iPhone XR,Battery drain,in_progress,2000,cash
"""
    headers, rows = extract_rows_from_file(csv_bytes, "test.csv")
    assert len(headers) == 9
    assert len(rows) == 2

    mapping = {
        "received_date": "Date",
        "customer_name": "Customer Name",
        "phone": "Phone",
        "device_brand": "Brand",
        "device_model": "Model",
        "reported_issue": "Issue",
        "amount": "Charge",
        "payment_mode": "Payment Mode",
    }

    # 1. Dry run
    res_dry = process_import(temp_db, headers, rows, mapping, dry_run=True)
    assert res_dry["valid_count"] == 2
    assert res_dry["error_count"] == 0

    # 2. Live import
    res_live = process_import(temp_db, headers, rows, mapping, dry_run=False)
    assert res_live["valid_count"] == 2
    assert res_live["error_count"] == 0

    # Check imported data
    cust = get_or_create_customer(temp_db, "9820011223", "Ramesh Patel")[0]
    assert len(cust.tickets) == 1
    t = cust.tickets[0]
    assert t.device_brand == "Samsung"


def test_ticket_updates_and_report_helpers(temp_db):
    """Test updating ticket fields, passcode clearing, and report comparison calculations."""
    from app.services.reports import compute_comparison_pct, get_previous_period_bounds
    from app.services.tickets import clear_ticket_passcode

    # Report helpers
    assert compute_comparison_pct(120, 100) == "+20.0%"
    assert compute_comparison_pct(80, 100) == "-20.0%"
    assert compute_comparison_pct(50, 0) == "n/a"

    p_from, p_to = get_previous_period_bounds(date(2026, 10, 1), date(2026, 10, 10))
    assert p_to == date(2026, 9, 30)
    assert (p_to - p_from).days + 1 == 10

    # Ticket updates
    t = create_ticket(
        db=temp_db,
        customer_phone="9820033445",
        customer_name="Update Target",
        device_brand="Xiaomi",
        device_model="Note 9",
        reported_issue="Initial issue",
        passcode="9876",
    )
    temp_db.commit()

    update_ticket_details(
        db=temp_db,
        ticket=t,
        device_brand="Xiaomi",
        device_model="Note 9 Pro",
        reported_issue="Updated issue description",
        issue_category="Screen",
        imei_or_serial="86450000000001",
        color="Glacier White",
        estimate_amount=2500,
        technician_note="Board looks clean",
        intake_condition={"scratches": "minor"},
    )
    temp_db.commit()

    assert t.device_model == "Note 9 Pro"
    assert t.color == "Glacier White"
    assert t.estimate_amount == 2500

    # Clear passcode
    clear_ticket_passcode(temp_db, t)
    temp_db.commit()
    assert t.passcode_encrypted is None


def test_queue_filtering_and_empty_state(temp_db):
    """Test that queue table does not show empty state banner when tickets exist, and does when empty."""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app
    from app.security import encode_session

    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Create a ticket in received status
        t = create_ticket(
            db=temp_db,
            customer_phone="9820011111",
            customer_name="Queue Tester",
            device_brand="Apple",
            device_model="iPhone 14",
            reported_issue="Battery replacement",
        )
        temp_db.commit()

        client = TestClient(app, cookies={"session": encode_session({"user_id": 1})})

        # 1. Default queue view should show the ticket and NOT show "No tickets in this status"
        resp = client.get("/")
        assert resp.status_code == 200
        assert "No tickets in this status" not in resp.text
        assert t.ticket_no in resp.text

        # 2. HTMX partial swap for queue table
        resp_partial = client.get("/", headers={"HX-Request": "true"})
        assert resp_partial.status_code == 200
        assert "No tickets in this status" not in resp_partial.text
        assert t.ticket_no in resp_partial.text

        # 3. Filtering by another status with 0 tickets (e.g. ready_for_pickup)
        resp_empty = client.get("/?filtered=1&status=ready_for_pickup", headers={"HX-Request": "true"})
        assert resp_empty.status_code == 200
        assert "No tickets in this status" in resp_empty.text

        # 4. Filtering with empty status (unchecked all)
        resp_none = client.get("/?filtered=1", headers={"HX-Request": "true"})
        assert resp_none.status_code == 200
        assert "No tickets in this status" in resp_none.text
    finally:
        app.dependency_overrides.clear()


def test_autocomplete_html_response(temp_db):
    """Test that autocomplete endpoints return HTML without JSON string quotes or escaped values."""
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app
    from app.security import encode_session

    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        create_ticket(
            db=temp_db,
            customer_phone="9820022222",
            customer_name="Brand User",
            device_brand="Samsung",
            device_model="Galaxy S22",
            reported_issue="Screen flickering",
        )
        temp_db.commit()

        client = TestClient(app, cookies={"session": encode_session({"user_id": 1})})

        resp_brands = client.get("/autocomplete/brands")
        assert resp_brands.status_code == 200
        assert "text/html" in resp_brands.headers.get("content-type", "")
        assert '<option value="Samsung">' in resp_brands.text
        assert '\\"Samsung\\"' not in resp_brands.text
        assert not resp_brands.text.startswith('"')

        resp_models = client.get("/autocomplete/models?device_brand=Samsung")
        assert resp_models.status_code == 200
        assert "text/html" in resp_models.headers.get("content-type", "")
        assert '<option value="Galaxy S22">' in resp_models.text
        assert not resp_models.text.startswith('"')
    finally:
        app.dependency_overrides.clear()


def test_inventory_service_validations(temp_db):
    from app.services.inventory import (
        add_inventory_item,
        adjust_inventory_stock,
        delete_inventory_item,
        edit_inventory_item,
        get_available_spares,
        list_inventory,
    )

    # Empty spare type
    with pytest.raises(ValidationFailed, match="Spare type/category is required"):
        add_inventory_item(temp_db, spare_type="", model="Pixel 7")

    # Long model
    with pytest.raises(ValidationFailed, match="between 1 and 100"):
        add_inventory_item(temp_db, spare_type="screen", model="x" * 101)

    # Negative quantity
    with pytest.raises(ValidationFailed, match="Quantity cannot be negative"):
        add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", quantity=-1)

    # Invalid cost price
    with pytest.raises(ValidationFailed, match="Cost price"):
        add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", cost_price=-5)

    with pytest.raises(ValidationFailed, match="Cost price"):
        add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", cost_price=10_00_001)

    # Invalid selling price
    with pytest.raises(ValidationFailed, match="Selling price"):
        add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", selling_price=-5)

    with pytest.raises(ValidationFailed, match="Selling price"):
        add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", selling_price=10_00_001)

    # Valid item
    item = add_inventory_item(temp_db, spare_type="screen", model="Pixel 7", quantity=2)

    # In stock filter & model filter
    assert len(list_inventory(temp_db, in_stock_only=True)) >= 1
    assert len(get_available_spares(temp_db, model="Pixel")) >= 1

    # Edit validations
    with pytest.raises(ValidationFailed):
        edit_inventory_item(temp_db, item, spare_type="", model="Pixel 7", quantity=2)
    with pytest.raises(ValidationFailed):
        edit_inventory_item(temp_db, item, spare_type="screen", model="", quantity=2)
    with pytest.raises(ValidationFailed):
        edit_inventory_item(temp_db, item, spare_type="screen", model="Pixel 7", quantity=-1)
    with pytest.raises(ValidationFailed):
        edit_inventory_item(temp_db, item, spare_type="screen", model="Pixel 7", quantity=2, cost_price=-1)
    with pytest.raises(ValidationFailed):
        edit_inventory_item(temp_db, item, spare_type="screen", model="Pixel 7", quantity=2, selling_price=-1)

    # Adjust / delete non-existent item ID
    with pytest.raises(ValidationFailed, match="Inventory item not found"):
        adjust_inventory_stock(temp_db, 999999, delta=1)

    with pytest.raises(ValidationFailed, match="Inventory item not found"):
        delete_inventory_item(temp_db, 999999)


def test_items_service_validations(temp_db):
    t = create_ticket(
        db=temp_db,
        customer_phone="9876543210",
        customer_name="Rohan",
        device_brand="Apple",
        device_model="iPhone 13",
        reported_issue="Broken screen",
    )

    # Description validation
    with pytest.raises(ValidationFailed, match="Item description"):
        add_item(temp_db, t, item_type="labor", description="", price_charged=500)
    with pytest.raises(ValidationFailed, match="Item description"):
        add_item(temp_db, t, item_type="labor", description="x" * 121, price_charged=500)

    # Price validation
    with pytest.raises(ValidationFailed, match="Price charged"):
        add_item(temp_db, t, item_type="labor", description="Repair", price_charged=-10)
    with pytest.raises(ValidationFailed, match="Price charged"):
        add_item(temp_db, t, item_type="labor", description="Repair", price_charged=10_00_001)

    # Item type validation
    with pytest.raises(ValidationFailed, match="labor or part"):
        add_item(temp_db, t, item_type="other", description="Repair", price_charged=500)

    # Part cost price validation
    with pytest.raises(ValidationFailed, match="Cost price"):
        add_item(temp_db, t, item_type="part", description="Screen", price_charged=500, cost_price=-10)

    # Non-existent inventory item
    with pytest.raises(ValidationFailed, match="Selected inventory item not found"):
        add_item(temp_db, t, item_type="part", description="Screen", price_charged=500, inventory_item_id=999999)

    # Edit item validations
    item = add_item(temp_db, t, item_type="part", description="Valid part", price_charged=500, cost_price=200)
    with pytest.raises(ValidationFailed, match="Description"):
        edit_item(temp_db, item, description="", price_charged=500)
    with pytest.raises(ValidationFailed, match="Price charged"):
        edit_item(temp_db, item, description="Valid part", price_charged=-1)
    with pytest.raises(ValidationFailed, match="Cost price"):
        edit_item(temp_db, item, description="Valid part", price_charged=500, cost_price=-1)


def test_backup_and_catchup_helpers(tmp_path):
    from pathlib import Path

    from app.services.backup import (
        create_backup,
        get_sqlite_source_path,
        run_startup_catchup_backup,
    )

    src = get_sqlite_source_path()
    assert isinstance(src, Path)

    # Non-existent source logs warning and returns target path
    non_existent = tmp_path / "does_not_exist.db"
    res = create_backup(src_path=non_existent, backup_dir=tmp_path / "backups")
    assert res.parent == tmp_path / "backups"

    # Catchup backup returns bool
    did_catchup = run_startup_catchup_backup()
    assert isinstance(did_catchup, bool)

