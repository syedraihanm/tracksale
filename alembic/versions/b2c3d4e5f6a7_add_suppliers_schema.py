"""add_suppliers_schema

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-14 23:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

import app.db
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add suppliers and supplier_payments tables, and link to ticket_items and inventory_items."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Create suppliers table if not exists
    if not inspector.has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("email", sa.String(length=100), nullable=True),
            sa.Column("contact_person", sa.String(length=100), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
            sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("suppliers", schema=None) as batch_op:
            batch_op.create_index("ix_suppliers_name", ["name"], unique=True)
            batch_op.create_index("ix_suppliers_is_deleted", ["is_deleted"], unique=False)

    # 2. Add anti-delete trigger on suppliers
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_suppliers
        BEFORE DELETE ON suppliers
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on suppliers; use soft delete');
        END;
        """
    )

    # 3. Create supplier_payments table if not exists
    if not inspector.has_table("supplier_payments"):
        op.create_table(
            "supplier_payments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("mode", sa.String(length=20), nullable=False, default="cash"),
            sa.Column("reference", sa.String(length=100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("paid_at", app.db.UTCDateTime(), nullable=False),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
            sa.Column("deleted_reason", sa.Text(), nullable=True),
            sa.Column("deleted_at", app.db.UTCDateTime(), nullable=True),
            sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
            sa.CheckConstraint("amount > 0", name="ck_supplier_payments_amount_pos"),
            sa.ForeignKeyConstraint(
                ["supplier_id"],
                ["suppliers.id"],
                name="fk_supplier_payments_supplier_id",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("supplier_payments", schema=None) as batch_op:
            batch_op.create_index("ix_supplier_payments_supplier_id", ["supplier_id"], unique=False)
            batch_op.create_index("ix_supplier_payments_paid_at", ["paid_at"], unique=False)
            batch_op.create_index("ix_supplier_payments_is_deleted", ["is_deleted"], unique=False)

    # 4. Add anti-delete trigger on supplier_payments
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_supplier_payments
        BEFORE DELETE ON supplier_payments
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on supplier_payments; use soft delete');
        END;
        """
    )

    # 5. Add supplier_id to ticket_items if not already present
    ticket_item_cols = [c["name"] for c in inspector.get_columns("ticket_items")]
    if "supplier_id" not in ticket_item_cols:
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_ticket_items;")
        with op.batch_alter_table("ticket_items", schema=None) as batch_op:
            batch_op.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_ticket_items_supplier_id",
                "suppliers",
                ["supplier_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_ticket_items_supplier_id", ["supplier_id"], unique=False)

        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_no_delete_ticket_items
            BEFORE DELETE ON ticket_items
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
            END;
            """
        )

    # 6. Add supplier_id to inventory_items if not already present
    if inspector.has_table("inventory_items"):
        inv_cols = [c["name"] for c in inspector.get_columns("inventory_items")]
        if "supplier_id" not in inv_cols:
            op.execute("DROP TRIGGER IF EXISTS trg_no_delete_inventory_items;")
            with op.batch_alter_table("inventory_items", schema=None) as batch_op:
                batch_op.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_inventory_items_supplier_id",
                    "suppliers",
                    ["supplier_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
                batch_op.create_index("ix_inventory_items_supplier_id", ["supplier_id"], unique=False)

            op.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_no_delete_inventory_items
                BEFORE DELETE ON inventory_items
                BEGIN
                    SELECT RAISE(ABORT, 'Hard delete is forbidden on inventory_items; use soft delete');
                END;
                """
            )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_supplier_payments;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_suppliers;")

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_items"):
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_inventory_items;")
        with op.batch_alter_table("inventory_items", schema=None) as batch_op:
            batch_op.drop_index("ix_inventory_items_supplier_id")
            batch_op.drop_constraint("fk_inventory_items_supplier_id", type_="foreignkey")
            batch_op.drop_column("supplier_id")
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_no_delete_inventory_items
            BEFORE DELETE ON inventory_items
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on inventory_items; use soft delete');
            END;
            """
        )

    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_ticket_items;")
    with op.batch_alter_table("ticket_items", schema=None) as batch_op:
        batch_op.drop_index("ix_ticket_items_supplier_id")
        batch_op.drop_constraint("fk_ticket_items_supplier_id", type_="foreignkey")
        batch_op.drop_column("supplier_id")
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_ticket_items
        BEFORE DELETE ON ticket_items
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
        END;
        """
    )

    with op.batch_alter_table("supplier_payments", schema=None) as batch_op:
        batch_op.drop_index("ix_supplier_payments_is_deleted")
        batch_op.drop_index("ix_supplier_payments_paid_at")
        batch_op.drop_index("ix_supplier_payments_supplier_id")
    op.drop_table("supplier_payments")

    with op.batch_alter_table("suppliers", schema=None) as batch_op:
        batch_op.drop_index("ix_suppliers_is_deleted")
        batch_op.drop_index("ix_suppliers_name")
    op.drop_table("suppliers")
