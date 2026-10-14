"""add_inventory_schema

Revision ID: a1b2c3d4e5f6
Revises: 99c02672819f
Create Date: 2026-10-14 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

import app.db
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "99c02672819f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema to add inventory_items and ticket_items.inventory_item_id."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Create inventory_items table if it does not exist
    if not inspector.has_table("inventory_items"):
        op.create_table(
            "inventory_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("spare_type", sa.String(length=50), nullable=False),
            sa.Column("model", sa.String(length=100), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, default=1),
            sa.Column("cost_price", sa.Integer(), nullable=False, default=0),
            sa.Column("selling_price", sa.Integer(), nullable=False, default=0),
            sa.Column("supplier_name", sa.String(length=100), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
            sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
            sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
            sa.CheckConstraint("quantity >= 0", name="ck_inventory_items_quantity"),
            sa.CheckConstraint("cost_price >= 0", name="ck_inventory_items_cost_price"),
            sa.CheckConstraint("selling_price >= 0", name="ck_inventory_items_selling_price"),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("inventory_items", schema=None) as batch_op:
            batch_op.create_index("ix_inventory_items_spare_type", ["spare_type"], unique=False)
            batch_op.create_index("ix_inventory_items_model", ["model"], unique=False)
            batch_op.create_index("ix_inventory_items_is_deleted", ["is_deleted"], unique=False)

    # 2. Add anti-delete trigger on inventory_items
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_inventory_items
        BEFORE DELETE ON inventory_items
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on inventory_items; use soft delete');
        END;
        """
    )

    # 3. Add inventory_item_id to ticket_items if not already present
    ticket_item_cols = [c["name"] for c in inspector.get_columns("ticket_items")]
    if "inventory_item_id" not in ticket_item_cols:
        # Drop trigger temporarily before batch table alteration on SQLite
        op.execute("DROP TRIGGER IF EXISTS trg_no_delete_ticket_items;")

        with op.batch_alter_table("ticket_items", schema=None) as batch_op:
            batch_op.add_column(sa.Column("inventory_item_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_ticket_items_inventory_item_id",
                "inventory_items",
                ["inventory_item_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_ticket_items_inventory_item_id", ["inventory_item_id"], unique=False)

        # Recreate trigger on ticket_items
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_no_delete_ticket_items
            BEFORE DELETE ON ticket_items
            BEGIN
                SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
            END;
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_inventory_items;")
    op.execute("DROP TRIGGER IF EXISTS trg_no_delete_ticket_items;")

    with op.batch_alter_table("ticket_items", schema=None) as batch_op:
        batch_op.drop_index("ix_ticket_items_inventory_item_id")
        batch_op.drop_constraint("fk_ticket_items_inventory_item_id", type_="foreignkey")
        batch_op.drop_column("inventory_item_id")

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_no_delete_ticket_items
        BEFORE DELETE ON ticket_items
        BEGIN
            SELECT RAISE(ABORT, 'Hard delete is forbidden on ticket_items; use soft delete');
        END;
        """
    )

    with op.batch_alter_table("inventory_items", schema=None) as batch_op:
        batch_op.drop_index("ix_inventory_items_is_deleted")
        batch_op.drop_index("ix_inventory_items_model")
        batch_op.drop_index("ix_inventory_items_spare_type")

    op.drop_table("inventory_items")
