from datetime import timedelta

from app.db import SessionLocal
from app.models.enums import TicketStatus
from app.models.ticket import Ticket
from app.services.reports import compute_reports
from app.timeutil import business_date


def test_seeded_data_metrics_invariants():
    """AC8: Cross-check report service calculations against seeded dataset invariants."""
    db = SessionLocal()
    try:
        today = business_date()
        from_d = today - timedelta(days=90)
        # Check overall 90-day dashboard metrics
        metrics = compute_reports(db, from_date=from_d, to_date=today)

        # Revenue invariants
        assert metrics["gross_revenue"] >= 0
        assert metrics["parts_cost"] >= 0
        assert metrics["gross_margin_rupees"] == metrics["billed_value"] - metrics["parts_cost"]

        # Fix success rate invariant
        if metrics["devices_serviced"] > 0:
            assert 0.0 <= metrics["fix_success_rate"] <= 100.0

        # Turnaround time
        assert metrics["avg_turnaround_hours"] >= 0
        assert metrics["avg_pickup_delay_hours"] >= 0

        # Active queue count invariant
        active_in_db = (
            db.query(Ticket)
            .filter(
                Ticket.is_deleted == False,
                Ticket.status.in_([
                    TicketStatus.RECEIVED.value,
                    TicketStatus.IN_PROGRESS.value,
                    TicketStatus.AWAITING_PARTS.value,
                    TicketStatus.READY_FOR_PICKUP.value,
                ]),
            )
            .count()
        )
        assert active_in_db > 0  # Seed script generated active tickets
    finally:
        db.close()
