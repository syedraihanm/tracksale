"""Use AMEE MOBILES defaults for shops that have not completed setup.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_DEFAULT_TERMS = (
    "1. Device is accepted at the owner's risk; please back up your data. "
    "2. Estimates may change after diagnosis and your approval will be sought. "
    "3. Repaired devices carry the warranty stated on this receipt for the repaired part/fault only; physical or water damage voids it. "
    "4. Please present this receipt or ticket number at pickup."
)
NEW_DEFAULT_TERMS = (
    "1. Estimates may change after diagnosis and your approval will be sought. "
    "2. Repaired devices carry the warranty stated on this receipt for the repaired part/fault only; physical or water damage voids it. "
    "4. Please present this receipt or ticket number at pickup."
)
OLD_DEFAULT_INTAKE = (
    "Hi {name}, we received your {device}. Ticket {ticket_no}. Issue: {issue}. "
    "Advance paid: ₹{advance}. Thank you, {shop_name}."
)
NEW_DEFAULT_INTAKE = (
    "Hi {name}, we received your {device}. Ticket {ticket_no}. Issue: {issue}. "
    "Thank you, {shop_name}."
)


def upgrade() -> None:
    """Update only untouched defaults on shops that have not completed setup."""
    op.get_bind().execute(
        sa.text(
            """
            UPDATE settings
            SET shop_name = CASE
                    WHEN setup_completed = 0 AND shop_name = :old_shop_name THEN :new_shop_name
                    ELSE shop_name
                END,
                receipt_terms_text = CASE
                    WHEN setup_completed = 0 AND receipt_terms_text = :old_terms THEN :new_terms
                    ELSE receipt_terms_text
                END,
                msg_template_intake = CASE
                    WHEN setup_completed = 0 AND msg_template_intake = :old_intake THEN :new_intake
                    ELSE msg_template_intake
                END
            WHERE id = 1
            """
        ),
        {
            "old_shop_name": "Mobile Repair Shop",
            "new_shop_name": "AMEE MOBILES",
            "old_terms": OLD_DEFAULT_TERMS,
            "new_terms": NEW_DEFAULT_TERMS,
            "old_intake": OLD_DEFAULT_INTAKE,
            "new_intake": NEW_DEFAULT_INTAKE,
        },
    )


def downgrade() -> None:
    """Keep shop-selected settings when downgrading this data-only revision."""
    pass
