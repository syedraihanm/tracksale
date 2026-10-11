from datetime import UTC, date, datetime

from app.models.customer import Customer
from app.models.enums import Outcome, PaymentKind, PaymentMode, TicketStatus
from app.models.payment import Payment
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.services.cash_close import close_cash_day
from app.services.reports import compute_reports
from app.timeutil import IST


def ist_dt(year, month, day, hour, minute) -> datetime:
    """Helper to create timezone-aware UTC datetime from given IST year/month/day/hour/minute."""
    dt_ist = datetime(year, month, day, hour, minute, tzinfo=IST)
    return dt_ist.astimezone(UTC)


def test_golden_dataset_metrics(temp_db):
    # Customer setup
    c1 = Customer(name="Customer 1", phone="9876543210")
    temp_db.add(c1)
    temp_db.commit()

    # T1: Samsung Galaxy A32 / Screen
    # received 02-Sep 10:00, ready 04-Sep 10:00, delivered 05-Sep 12:00, repaired, warranty_days=30
    t1 = Ticket(
        ticket_no="R-1001",
        customer_id=c1.id,
        device_brand="Samsung",
        device_model="Galaxy A32",
        reported_issue="Broken screen",
        issue_category="Screen",
        intake_condition={},
        status=TicketStatus.DELIVERED.value,
        outcome=Outcome.REPAIRED.value,
        received_at=ist_dt(2026, 9, 2, 10, 0),
        ready_at=ist_dt(2026, 9, 4, 10, 0),
        delivered_at=ist_dt(2026, 9, 5, 12, 0),
        warranty_days=30,
        warranty_until=date(2026, 10, 5),  # 05-Sep + 30 days
        is_deleted=False,
    )
    temp_db.add(t1)
    temp_db.flush()

    # T1 items: labor ₹500; part "Display replacement" price ₹2,500, cost ₹1,800
    temp_db.add_all([
        TicketItem(ticket_id=t1.id, type="labor", description="Screen repair labor", price_charged=500, cost_price=0),
        TicketItem(ticket_id=t1.id, type="part", description="Display replacement", price_charged=2500, cost_price=1800),
    ])

    # T1 payments: ₹1,000 cash advance 02-Sep; ₹2,000 UPI final 05-Sep
    temp_db.add_all([
        Payment(ticket_id=t1.id, amount=1000, mode=PaymentMode.CASH.value, kind=PaymentKind.ADVANCE.value, paid_at=ist_dt(2026, 9, 2, 10, 30)),
        Payment(ticket_id=t1.id, amount=2000, mode=PaymentMode.UPI.value, kind=PaymentKind.FINAL.value, paid_at=ist_dt(2026, 9, 5, 12, 15)),
    ])

    # T2: Redmi Note 11 / Battery
    # received 03-Sep 10:00, ready 03-Sep 18:00, delivered 08-Sep 18:00, repaired, warranty_days=30
    t2 = Ticket(
        ticket_no="R-1002",
        customer_id=c1.id,
        device_brand="Redmi",
        device_model="Note 11",
        reported_issue="Battery draining fast",
        issue_category="Battery",
        intake_condition={},
        status=TicketStatus.DELIVERED.value,
        outcome=Outcome.REPAIRED.value,
        received_at=ist_dt(2026, 9, 3, 10, 0),
        ready_at=ist_dt(2026, 9, 3, 18, 0),
        delivered_at=ist_dt(2026, 9, 8, 18, 0),
        warranty_days=30,
        warranty_until=date(2026, 10, 8),
        is_deleted=False,
    )
    temp_db.add(t2)
    temp_db.flush()

    # T2 items: labor ₹400; part "Battery replacement" price ₹1,600, cost ₹1,100
    temp_db.add_all([
        TicketItem(ticket_id=t2.id, type="labor", description="Battery labor", price_charged=400, cost_price=0),
        TicketItem(ticket_id=t2.id, type="part", description="Battery replacement", price_charged=1600, cost_price=1100),
    ])

    # T2 payments: ₹2,000 card final 08-Sep; refund ₹200 cash 09-Sep (note "goodwill")
    temp_db.add_all([
        Payment(ticket_id=t2.id, amount=2000, mode=PaymentMode.CARD.value, kind=PaymentKind.FINAL.value, paid_at=ist_dt(2026, 9, 8, 18, 5)),
        Payment(ticket_id=t2.id, amount=-200, mode=PaymentMode.CASH.value, kind=PaymentKind.REFUND.value, note="goodwill", paid_at=ist_dt(2026, 9, 9, 11, 0)),
    ])

    # T3: Vivo Y20 / Software
    # received 04-Sep 10:00, declined 04-Sep 15:00, delivered 04-Sep 16:00
    t3 = Ticket(
        ticket_no="R-1003",
        customer_id=c1.id,
        device_brand="Vivo",
        device_model="Y20",
        reported_issue="Bootloop",
        issue_category="Software",
        intake_condition={},
        status=TicketStatus.DELIVERED.value,
        outcome=Outcome.DECLINED.value,
        received_at=ist_dt(2026, 9, 4, 10, 0),
        ready_at=None,
        delivered_at=ist_dt(2026, 9, 4, 16, 0),
        warranty_days=30,
        warranty_until=None,
        is_deleted=False,
    )
    temp_db.add(t3)
    temp_db.flush()
    temp_db.add(StatusHistory(ticket_id=t3.id, from_status=TicketStatus.RECEIVED.value, to_status=TicketStatus.DECLINED.value, changed_at=ist_dt(2026, 9, 4, 15, 0)))

    # T3 items: labor "Diagnostic fee" ₹150
    temp_db.add(TicketItem(ticket_id=t3.id, type="labor", description="Diagnostic fee", price_charged=150, cost_price=0))
    # T3 payment: ₹150 cash final 04-Sep
    temp_db.add(Payment(ticket_id=t3.id, amount=150, mode=PaymentMode.CASH.value, kind=PaymentKind.FINAL.value, paid_at=ist_dt(2026, 9, 4, 16, 5)))

    # T4: Samsung Galaxy A32 / Water damage
    # received 05-Sep 10:00, unrepairable 05-Sep 16:00, delivered 10-Sep 12:00
    t4 = Ticket(
        ticket_no="R-1004",
        customer_id=c1.id,
        device_brand="Samsung",
        device_model="Galaxy A32",
        reported_issue="Dropped in water",
        issue_category="Water damage",
        intake_condition={},
        status=TicketStatus.DELIVERED.value,
        outcome=Outcome.UNREPAIRABLE.value,
        received_at=ist_dt(2026, 9, 5, 10, 0),
        ready_at=None,
        delivered_at=ist_dt(2026, 9, 10, 12, 0),
        warranty_days=30,
        warranty_until=None,
        is_deleted=False,
    )
    temp_db.add(t4)
    temp_db.flush()
    temp_db.add(StatusHistory(ticket_id=t4.id, from_status=TicketStatus.RECEIVED.value, to_status=TicketStatus.UNREPAIRABLE.value, changed_at=ist_dt(2026, 9, 5, 16, 0)))

    # T5: Samsung Galaxy A32 / Screen (child of T1)
    # received 20-Sep, still received
    t5 = Ticket(
        ticket_no="R-1005",
        customer_id=c1.id,
        device_brand="Samsung",
        device_model="Galaxy A32",
        reported_issue="Screen touch flickering",
        issue_category="Screen",
        intake_condition={},
        status=TicketStatus.RECEIVED.value,
        received_at=ist_dt(2026, 9, 20, 14, 0),
        parent_ticket_id=t1.id,
        warranty_days=30,
        is_deleted=False,
    )
    temp_db.add(t5)

    # Cash closings:
    # 04-Sep opening ₹4,000, counted ₹4,150
    close_cash_day(temp_db, date(2026, 9, 4), opening_cash=4000, counted_cash=4150, now=ist_dt(2026, 9, 4, 21, 0))
    # 05-Sep opening (default) ₹4,150, counted ₹4,100
    close_cash_day(temp_db, date(2026, 9, 5), opening_cash=4150, counted_cash=4100, now=ist_dt(2026, 9, 5, 21, 0))
    # 09-Sep opening (default, from 05-Sep) ₹4,100, counted ₹3,950
    close_cash_day(temp_db, date(2026, 9, 9), opening_cash=4100, counted_cash=3950, now=ist_dt(2026, 9, 9, 21, 0))

    temp_db.commit()

    # Now compute reports for 01-Sep-2026 to 30-Sep-2026
    rep = compute_reports(temp_db, date(2026, 9, 1), date(2026, 9, 30))

    # Assertions from Section 14.3:
    assert rep["gross_revenue"] == 4950
    assert rep["billed_value"] == 5150
    assert rep["parts_cost"] == 2900
    assert rep["gross_margin_rupees"] == 2250
    assert rep["gross_margin_pct"] == 43.7

    # Modes: cash ₹950 (19.2%), card ₹2,000 (40.4%), UPI ₹2,000 (40.4%)
    assert rep["mode_totals"][PaymentMode.CASH.value] == 950
    assert rep["mode_totals"][PaymentMode.CARD.value] == 2000
    assert rep["mode_totals"][PaymentMode.UPI.value] == 2000
    assert rep["mode_percentages"][PaymentMode.CASH.value] == 19.2
    assert rep["mode_percentages"][PaymentMode.CARD.value] == 40.4
    assert rep["mode_percentages"][PaymentMode.UPI.value] == 40.4

    # Devices serviced 2
    assert rep["devices_serviced"] == 2
    # Avg turnaround 28 hours (48h and 8h)
    assert rep["avg_turnaround_hours"] == 28.0
    # Avg pickup delay 73 hours (26h and 120h)
    assert rep["avg_pickup_delay_hours"] == 73.0

    # Fix success 1 of 2 = 50%
    assert rep["fix_success_rate"] == 50.0
    assert rep["repaired_without_warranty_return"] == 1
    assert rep["declined_count"] == 1
    assert rep["unrepairable_count"] == 1

    # Top brands: Samsung 3, Redmi 1, Vivo 1
    brands_dict = dict(rep["top_brands"])
    assert brands_dict["Samsung"] == 3
    assert brands_dict["Redmi"] == 1
    assert brands_dict["Vivo"] == 1

    # Top model: Galaxy A32 (3)
    models_dict = dict(rep["top_models"])
    assert models_dict["Galaxy A32"] == 3

    # Issues: Screen 2, Battery 1, Software 1, Water damage 1
    issues_dict = dict(rep["top_issues"])
    assert issues_dict["Screen"] == 2
    assert issues_dict["Battery"] == 1
    assert issues_dict["Software"] == 1
    assert issues_dict["Water damage"] == 1

    # Most-bought parts: Display replacement (1, ₹1,800), Battery replacement (1, ₹1,100)
    assert len(rep["most_bought_parts"]) == 2
    assert rep["most_bought_parts"][0]["description"] == "Display replacement"
    assert rep["most_bought_parts"][0]["total_cost"] == 1800
    assert rep["most_bought_parts"][1]["description"] == "Battery replacement"
    assert rep["most_bought_parts"][1]["total_cost"] == 1100

    # Daily revenue: 02-Sep ₹1,000; 04-Sep ₹150; 05-Sep ₹2,000; 08-Sep ₹2,000; 09-Sep -₹200; all other days ₹0
    daily_map = {d["full_date"]: d["amount"] for d in rep["daily_trend"]}
    assert daily_map["2026-09-02"] == 1000
    assert daily_map["2026-09-04"] == 150
    assert daily_map["2026-09-05"] == 2000
    assert daily_map["2026-09-08"] == 2000
    assert daily_map["2026-09-09"] == -200
    assert daily_map["2026-09-01"] == 0
    assert daily_map["2026-09-15"] == 0

    # Cash closings: 04-Sep expected ₹4,150, variance 0; 05-Sep expected ₹4,150, variance -50; 09-Sep expected ₹3,900, variance +50
    var_map = {v["raw_date"]: (v["expected"], v["variance"]) for v in rep["variance_history"]}
    assert var_map["2026-09-04"] == (4150, 0)
    assert var_map["2026-09-05"] == (4150, -50)
    assert var_map["2026-09-09"] == (3900, 50)
