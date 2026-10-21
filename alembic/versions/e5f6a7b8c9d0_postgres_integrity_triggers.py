"""Add PostgreSQL equivalents of the SQLite integrity triggers.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROTECTED_TABLES = (
    "tickets",
    "payments",
    "ticket_items",
    "status_history",
    "audit_log",
    "inventory_items",
    "suppliers",
    "supplier_payments",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_hard_delete() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Hard delete is forbidden on %; use the audited soft-delete action', TG_TABLE_NAME;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Audit log is append-only';
        END;
        $$;
        """
    )

    for table_name in PROTECTED_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_no_delete_{table_name} "
            f"BEFORE DELETE ON {table_name} FOR EACH ROW EXECUTE FUNCTION reject_hard_delete()"
        )
    op.execute(
        "CREATE TRIGGER trg_no_update_audit_log "
        "BEFORE UPDATE ON audit_log FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table_name in PROTECTED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_no_delete_{table_name} ON {table_name}")
    op.execute("DROP TRIGGER IF EXISTS trg_no_update_audit_log ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_log_mutation()")
    op.execute("DROP FUNCTION IF EXISTS reject_hard_delete()")
