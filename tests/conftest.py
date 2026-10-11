import os
import tempfile

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import (
    Base,
    set_sqlite_immediate_transaction,
    set_sqlite_pragmas,
)
from app.models.settings import Settings as SettingsModel


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database with all tables and triggers."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", set_sqlite_pragmas)
    event.listen(engine, "begin", set_sqlite_immediate_transaction)

    Base.metadata.create_all(bind=engine)

    # Add triggers & settings row
    with engine.connect() as conn:
        conn.execute(
            SettingsModel.__table__.insert().values(
                id=1,
                shop_name="Mobile Repair Shop",
                shop_phone="9876543210",
                shop_address="123 Market Road",
                receipt_terms_text="Terms",
                default_warranty_days=30,
                owner_pin_hash=None,
                admin_password_hash=None,
                ticket_no_prefix="R",
                next_ticket_seq=1001,
                msg_template_intake="Intake msg {ticket_no}",
                msg_template_ready="Ready msg {ticket_no}",
                setup_completed=False,
            )
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_delete_tickets
            BEFORE DELETE ON tickets
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on tickets; use soft delete');
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_delete_payments
            BEFORE DELETE ON payments
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on payments; use soft delete');
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_delete_ticket_items
            BEFORE DELETE ON ticket_items
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_delete_status_history
            BEFORE DELETE ON status_history
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on status_history');
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_delete_audit_log
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on audit_log; audit log is append-only');
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE TRIGGER trg_no_update_audit_log
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'Update is forbidden on audit_log; audit log is append-only');
            END;
            """)
        )
        conn.commit()


    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = Session()

    yield session

    session.close()
    engine.dispose()
    try:
        os.remove(db_path)
    except OSError:
        pass
