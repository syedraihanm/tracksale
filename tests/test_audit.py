import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.audit_log import AuditLog
from app.models.enums import TicketStatus
from app.models.settings import Settings as SettingsModel
from app.security import hash_secret
from app.services.items import add_item, edit_item
from app.services.status import transition_ticket
from app.services.tickets import create_ticket, delete_ticket, reveal_ticket_passcode


def test_audit_logging_and_soft_delete(temp_db):
    """AC7: Verify full audit trail and soft delete mechanics with hard delete prevention."""
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.owner_pin_hash = hash_secret("1234")
    temp_db.commit()

    # 1. Create ticket -> creates audit row
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820098765",
        customer_name="Audit Tester",
        device_brand="Samsung",
        device_model="A52",
        reported_issue="Broken speaker",
        passcode="1234",
    )
    temp_db.commit()

    audits = temp_db.query(AuditLog).filter_by(ticket_id=ticket.id).all()
    assert any(a.entity == "ticket" and a.action == "create" for a in audits)

    # 2. Reveal passcode -> creates audit row
    reveal_ticket_passcode(temp_db, ticket)
    temp_db.commit()
    audits = temp_db.query(AuditLog).filter_by(ticket_id=ticket.id).all()
    assert any(a.action == "update" and "passcode" in (a.reason or "").lower() for a in audits)

    # 3. Add item & edit item -> creates audit rows
    item = add_item(temp_db, ticket, item_type="labor", description="Speaker fix", price_charged=500)
    temp_db.commit()
    edit_item(temp_db, item, description="Speaker replacement", price_charged=600)
    temp_db.commit()
    audits = temp_db.query(AuditLog).filter_by(ticket_id=ticket.id).all()
    assert any(a.entity == "item" and a.action == "create" for a in audits)
    assert any(a.entity == "item" and a.action == "update" for a in audits)

    # 4. Status transition -> creates audit row
    transition_ticket(temp_db, ticket, TicketStatus.IN_PROGRESS.value, note="Work started")
    temp_db.commit()
    audits = temp_db.query(AuditLog).filter_by(ticket_id=ticket.id).all()
    assert any(a.entity == "ticket" and a.action == "update" for a in audits)

    # 5. Soft delete ticket
    delete_ticket(temp_db, ticket, reason="Created by mistake", owner_pin="1234")
    temp_db.commit()
    assert ticket.is_deleted is True
    assert ticket.deleted_reason == "Created by mistake"
    audits = temp_db.query(AuditLog).filter_by(ticket_id=ticket.id).all()
    assert any(a.entity == "ticket" and a.action == "delete" for a in audits)


def test_sqlite_triggers_prevent_hard_deletes_and_updates(temp_db):
    """Verify database-level SQLite triggers reject DELETE on core tables and UPDATE/DELETE on audit_log."""
    # Ensure at least one audit row exists
    ticket = create_ticket(
        db=temp_db,
        customer_phone="9820011223",
        customer_name="Trigger Tester",
        device_brand="Brand",
        device_model="Model",
        reported_issue="Issue",
    )
    temp_db.commit()

    # Attempt hard DELETE on tickets table
    with pytest.raises(DBAPIError) as exc:
        temp_db.execute(text(f"DELETE FROM tickets WHERE id = {ticket.id}"))
        temp_db.commit()
    assert "Hard delete is forbidden on tickets" in str(exc.value)
    temp_db.rollback()

    # Attempt UPDATE on audit_log
    audit = temp_db.query(AuditLog).first()
    assert audit is not None
    with pytest.raises(DBAPIError) as exc:
        temp_db.execute(text(f"UPDATE audit_log SET reason = 'Tampered' WHERE id = {audit.id}"))
        temp_db.commit()
    assert "Update is forbidden on audit_log" in str(exc.value)
    temp_db.rollback()

    # Attempt hard DELETE on audit_log
    with pytest.raises(DBAPIError) as exc:
        temp_db.execute(text(f"DELETE FROM audit_log WHERE id = {audit.id}"))
        temp_db.commit()
    assert "Hard delete is forbidden on audit_log" in str(exc.value)
    temp_db.rollback()
