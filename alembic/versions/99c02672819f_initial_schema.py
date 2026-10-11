"""initial_schema

Revision ID: 99c02672819f
Revises: 
Create Date: 2026-10-10 15:56:37.750577

"""
from collections.abc import Sequence

import sqlalchemy as sa

import app.db
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '99c02672819f'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('entity', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Integer(), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=20), nullable=False),
    sa.Column('changed_fields', sa.JSON(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('timestamp', app.db.UTCDateTime(), nullable=False),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index('ix_audit_log_entity_id', ['entity', 'entity_id'], unique=False)
        batch_op.create_index('ix_audit_log_ticket_id', ['ticket_id'], unique=False)
        batch_op.create_index('ix_audit_log_timestamp', ['timestamp'], unique=False)

    op.create_table('cash_closings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('opening_cash', sa.Integer(), nullable=False),
    sa.Column('expected_cash', sa.Integer(), nullable=False),
    sa.Column('counted_cash', sa.Integer(), nullable=False),
    sa.Column('variance', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('is_closed', sa.Boolean(), nullable=False),
    sa.Column('closed_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('reopened_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('cash_closings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_cash_closings_date'), ['date'], unique=True)

    op.create_table('customers',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customers_phone'), ['phone'], unique=True)

    op.create_table('settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shop_name', sa.String(length=100), nullable=False),
    sa.Column('shop_phone', sa.String(length=30), nullable=False),
    sa.Column('shop_address', sa.Text(), nullable=False),
    sa.Column('receipt_terms_text', sa.Text(), nullable=False),
    sa.Column('default_warranty_days', sa.Integer(), nullable=False),
    sa.Column('owner_pin_hash', sa.String(length=255), nullable=True),
    sa.Column('admin_password_hash', sa.String(length=255), nullable=True),
    sa.Column('ticket_no_prefix', sa.String(length=10), nullable=False),
    sa.Column('next_ticket_seq', sa.Integer(), nullable=False),
    sa.Column('msg_template_intake', sa.Text(), nullable=False),
    sa.Column('msg_template_ready', sa.Text(), nullable=False),
    sa.Column('setup_completed', sa.Boolean(), nullable=False),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tickets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_no', sa.String(length=30), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('device_brand', sa.String(length=60), nullable=False),
    sa.Column('device_model', sa.String(length=60), nullable=False),
    sa.Column('imei_or_serial', sa.String(length=30), nullable=True),
    sa.Column('color', sa.String(length=30), nullable=True),
    sa.Column('passcode_encrypted', sa.Text(), nullable=True),
    sa.Column('reported_issue', sa.Text(), nullable=False),
    sa.Column('issue_category', sa.String(length=50), nullable=False),
    sa.Column('intake_condition', sa.JSON(), nullable=False),
    sa.Column('estimate_amount', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=True),
    sa.Column('technician_note', sa.Text(), nullable=True),
    sa.Column('received_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('ready_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('delivered_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('warranty_days', sa.Integer(), nullable=False),
    sa.Column('warranty_until', sa.Date(), nullable=True),
    sa.Column('parent_ticket_id', sa.Integer(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('deleted_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['parent_ticket_id'], ['tickets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tickets_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_delivered_at'), ['delivered_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_imei_or_serial'), ['imei_or_serial'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_is_deleted'), ['is_deleted'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_parent_ticket_id'), ['parent_ticket_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_received_at'), ['received_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_tickets_ticket_no'), ['ticket_no'], unique=True)

    op.create_table('payments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('paid_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_reason', sa.Text(), nullable=True),
    sa.Column('deleted_at', app.db.UTCDateTime(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.CheckConstraint("amount <> 0 AND ((kind = 'refund' AND amount < 0) OR (kind <> 'refund' AND amount > 0))", name='ck_payments_amount_kind_sign'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index('ix_payments_mode_paid_at', ['mode', 'paid_at'], unique=False)
        batch_op.create_index('ix_payments_paid_at', ['paid_at'], unique=False)
        batch_op.create_index('ix_payments_ticket_id', ['ticket_id'], unique=False)

    op.create_table('status_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('from_status', sa.String(length=30), nullable=True),
    sa.Column('to_status', sa.String(length=30), nullable=False),
    sa.Column('changed_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('status_history', schema=None) as batch_op:
        batch_op.create_index('ix_status_history_ticket_id', ['ticket_id'], unique=False)

    op.create_table('ticket_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('description', sa.String(length=120), nullable=False),
    sa.Column('price_charged', sa.Integer(), nullable=False),
    sa.Column('cost_price', sa.Integer(), nullable=False),
    sa.Column('supplier_name', sa.String(length=100), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('created_at', app.db.UTCDateTime(), nullable=False),
    sa.Column('updated_at', app.db.UTCDateTime(), nullable=False),
    sa.CheckConstraint("type = 'part' OR (cost_price = 0 AND supplier_name IS NULL)", name='ck_ticket_items_labor_cost_supplier'),
    sa.CheckConstraint('cost_price >= 0', name='ck_ticket_items_cost_price'),
    sa.CheckConstraint('price_charged >= 0', name='ck_ticket_items_price_charged'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ticket_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ticket_items_ticket_id'), ['ticket_id'], unique=False)

    # Insert default settings row
    op.execute(
        """
        INSERT INTO settings (
            id, shop_name, shop_phone, shop_address, receipt_terms_text,
            default_warranty_days, owner_pin_hash, admin_password_hash,
            ticket_no_prefix, next_ticket_seq, msg_template_intake,
            msg_template_ready, setup_completed, created_at, updated_at
        ) VALUES (
            1, 'Mobile Repair Shop', '', '',
            '1. Device is accepted at the owner''s risk; please back up your data. 2. Estimates may change after diagnosis and your approval will be sought. 3. Repaired devices carry the warranty stated on this receipt for the repaired part/fault only; physical or water damage voids it. 4. Please present this receipt or ticket number at pickup.',
            30, NULL, NULL, 'R', 1001,
            'Hi {name}, we received your {device}. Ticket {ticket_no}. Issue: {issue}. Advance paid: ₹{advance}. Thank you, {shop_name}.',
            'Hi {name}, your {device} is ready for pickup. Ticket {ticket_no}. Amount due: ₹{due}. {shop_name}',
            0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        );
        """
    )

    # Integrity triggers for SQLite
    op.execute(
        """
        CREATE TRIGGER trg_no_delete_tickets
        BEFORE DELETE ON tickets
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on tickets; use soft delete');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_no_delete_payments
        BEFORE DELETE ON payments
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on payments; use soft delete');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_no_delete_ticket_items
        BEFORE DELETE ON ticket_items
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_no_delete_status_history
        BEFORE DELETE ON status_history
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on status_history');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_no_delete_audit_log
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on audit_log; audit log is append-only');
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_no_update_audit_log
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Update is forbidden on audit_log; audit log is append-only');
        END;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_no_update_audit_log;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_audit_log;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_status_history;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_ticket_items;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_payments;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_tickets;")

    with op.batch_alter_table('ticket_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ticket_items_ticket_id'))
    op.drop_table('ticket_items')

    with op.batch_alter_table('status_history', schema=None) as batch_op:
        batch_op.drop_index('ix_status_history_ticket_id')
    op.drop_table('status_history')

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index('ix_payments_ticket_id')
        batch_op.drop_index('ix_payments_paid_at')
        batch_op.drop_index('ix_payments_mode_paid_at')
    op.drop_table('payments')

    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tickets_ticket_no'))
        batch_op.drop_index(batch_op.f('ix_tickets_status'))
        batch_op.drop_index(batch_op.f('ix_tickets_received_at'))
        batch_op.drop_index(batch_op.f('ix_tickets_parent_ticket_id'))
        batch_op.drop_index(batch_op.f('ix_tickets_is_deleted'))
        batch_op.drop_index(batch_op.f('ix_tickets_imei_or_serial'))
        batch_op.drop_index(batch_op.f('ix_tickets_delivered_at'))
        batch_op.drop_index(batch_op.f('ix_tickets_customer_id'))
    op.drop_table('tickets')

    op.drop_table('settings')

    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customers_phone'))
    op.drop_table('customers')

    with op.batch_alter_table('cash_closings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_cash_closings_date'))
    op.drop_table('cash_closings')

    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_log_timestamp')
        batch_op.drop_index('ix_audit_log_ticket_id')
        batch_op.drop_index('ix_audit_log_entity_id')
    op.drop_table('audit_log')
