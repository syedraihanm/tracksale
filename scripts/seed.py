"""Deterministic seed script for Mobile Repair Shop.

Generates realistic historical data over 3 months using service functions.
Refuses to run on a non-empty DB unless --reset is passed.
"""

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.config import Config
from sqlalchemy import func

from alembic import command
from app.db import SessionLocal, engine
from app.models.enums import PaymentKind, TicketStatus
from app.models.settings import Settings as SettingsModel
from app.models.ticket import Ticket
from app.security import hash_secret
from app.services.cash_close import close_cash_day
from app.services.items import add_item
from app.services.payments import add_payment, delete_payment
from app.services.status import transition_ticket
from app.services.tickets import create_ticket, delete_ticket
from app.timeutil import IST, business_date, utc_now

CUSTOMER_DATA = [
    ("Aarav Sharma", "9820112345"),
    ("Priya Patel", "9820223456"),
    ("Rohan Verma", "9820334567"),
    ("Sneha Kulkarni", "9820445678"),
    ("Vikram Singh", "9820556789"),
    ("Ananya Iyer", "9820667890"),
    ("Rahul Nair", "9820778901"),
    ("Pooja Gupta", "9820889012"),
    ("Amit Deshmukh", "9820990123"),
    ("Neha Joshi", "9821001234"),
    ("Suresh Reddy", "9821112345"),
    ("Kavita Rao", "9821223456"),
    ("Deepak Mehta", "9821334567"),
    ("Sunita Pillai", "9821445678"),
    ("Manoj Kumar", "9821556789"),
    ("Divya Agarwal", "9821667890"),
    ("Rajesh Chauhan", "9821778901"),
    ("Swati Bhatt", "9821889012"),
    ("Nitin Saxena", "9821990123"),
    ("Shilpa Menon", "9822001234"),
    ("Gaurav Mishra", "9822112345"),
    ("Meera Kapoor", "9822223456"),
    ("Alok Pandey", "9822334567"),
    ("Ritu Choudhary", "9822445678"),
    ("Kunal Shah", "9822556789"),
    ("Tarun Bose", "9822667890"),
    ("Sangeeta Das", "9822778901"),
    ("Vikas Yadav", "9822889012"),
]

DEVICES = [
    ("Samsung", "Galaxy M31"),
    ("Samsung", "Galaxy A32"),
    ("Samsung", "Galaxy S21"),
    ("Redmi", "Note 10"),
    ("Redmi", "Note 11"),
    ("Redmi", "Note 12"),
    ("Realme", "9 Pro"),
    ("Realme", "Narzo 50"),
    ("Vivo", "Y20"),
    ("Vivo", "V21"),
    ("Oppo", "F19 Pro"),
    ("OnePlus", "Nord CE 2"),
    ("OnePlus", "Nord 2"),
    ("Apple", "iPhone 11"),
    ("Apple", "iPhone 12"),
    ("Apple", "iPhone 13"),
    ("Motorola", "G52"),
    ("Poco", "X4 Pro"),
]

REPAIR_RECIPES = [
    {
        "issue": "Screen broken after drop",
        "category": "Screen",
        "labor": 500,
        "part_desc": "Display Assembly (Original quality)",
        "part_price": 2800,
        "part_cost": 2000,
        "supplier": "Metro Screen Wholesalers",
    },
    {
        "issue": "Battery draining in 2 hours",
        "category": "Battery",
        "labor": 350,
        "part_desc": "OEM Replacement Battery 5000mAh",
        "part_price": 1200,
        "part_cost": 850,
        "supplier": "PowerTech Spares",
    },
    {
        "issue": "Charging port loose, not charging",
        "category": "Charging port",
        "labor": 300,
        "part_desc": "Type-C Charging Sub-board Flex",
        "part_price": 500,
        "part_cost": 320,
        "supplier": "FastFix Spares",
    },
    {
        "issue": "Phone restarts constantly (bootloop)",
        "category": "Software",
        "labor": 450,
        "part_desc": None,
        "part_price": 0,
        "part_cost": 0,
        "supplier": None,
    },
    {
        "issue": "Dropped in water, no display",
        "category": "Water damage",
        "labor": 700,
        "part_desc": "Motherboard Ultrasonic Cleaning & IC Reballing",
        "part_price": 1200,
        "part_cost": 400,
        "supplier": "TechLab Supplies",
    },
    {
        "issue": "Earpiece speaker cracking sound",
        "category": "Speaker/Mic",
        "labor": 250,
        "part_desc": "Ear Speaker Module",
        "part_price": 350,
        "part_cost": 180,
        "supplier": "FastFix Spares",
    },
    {
        "issue": "Back camera blurry / not focusing",
        "category": "Camera",
        "labor": 400,
        "part_desc": "Rear Camera Module",
        "part_price": 1800,
        "part_cost": 1250,
        "supplier": "Vision Optics India",
    },
    {
        "issue": "No power, charging IC burnt",
        "category": "Motherboard",
        "labor": 900,
        "part_desc": "PMIC Power Management IC",
        "part_price": 1100,
        "part_cost": 650,
        "supplier": "Chipset Hub",
    },
]


def seed_database(reset: bool = False):
    random.seed(42)

    if reset:
        print("Resetting database...")
        engine.dispose()
        for f in Path("data").glob("shop.db*"):
            try:
                f.unlink()
            except OSError:
                pass
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")

    session = SessionLocal()

    try:
        # Check non-empty
        ticket_count = session.query(func.count(Ticket.id)).scalar() or 0
        if ticket_count > 0 and not reset:
            print("Database is not empty. Re-run with --reset to wipe and re-seed.")
            sys.exit(1)

        # Update Settings
        setting = session.query(SettingsModel).filter_by(id=1).first()
        if not setting:
            setting = SettingsModel(id=1)
            session.add(setting)
        setting.shop_name = "Apex Mobile Care"
        setting.shop_phone = "9820098200"
        setting.shop_address = "Shop #4, Galaxy Plaza, Station Road, Mumbai"
        setting.default_warranty_days = 30
        setting.admin_password_hash = hash_secret("demo12345")
        setting.owner_pin_hash = hash_secret("1234")
        setting.setup_completed = True
        session.commit()

        today = business_date()
        # 3-month span: 85 days ago to today
        start_date = today - timedelta(days=85)
        print(f"Seeding historical tickets from {start_date} to {today}...")

        repaired_pool = []
        all_created_tickets = []

        day_cursor = start_date
        while day_cursor < today:
            tickets_today = random.choices([0, 1, 2], weights=[20, 50, 30])[0]
            for _ in range(tickets_today):
                cust_name, cust_phone = random.choice(CUSTOMER_DATA)
                brand, model = random.choice(DEVICES)
                recipe = random.choice(REPAIR_RECIPES)

                t_hour = random.randint(10, 17)
                t_minute = random.randint(0, 50)
                intake_ist = datetime.combine(day_cursor, datetime.min.time(), tzinfo=IST) + timedelta(hours=t_hour, minutes=t_minute)
                intake_utc = intake_ist.astimezone(UTC)

                has_advance = random.random() < 0.4
                adv_amt = 500 if has_advance else 0
                adv_mode = random.choice(["cash", "upi"]) if has_advance else "cash"
                passcode = random.choice(["1234", "0000", "7896", "4561", None])

                t = create_ticket(
                    db=session,
                    customer_phone=cust_phone,
                    customer_name=cust_name,
                    device_brand=brand,
                    device_model=model,
                    reported_issue=recipe["issue"],
                    issue_category=recipe["category"],
                    imei_or_serial=f"8645{random.randint(1000000000, 9999999999)}",
                    color=random.choice(["Black", "Blue", "Silver", "Midnight"]),
                    passcode=passcode,
                    estimate_amount=recipe["labor"] + recipe["part_price"],
                    advance_amount=adv_amt,
                    advance_mode=adv_mode,
                    now=intake_utc,
                )
                session.commit()

                # Add labor item
                add_item(
                    db=session,
                    ticket=t,
                    item_type="labor",
                    description=f"{recipe['category']} service labor",
                    price_charged=recipe["labor"],
                    now=intake_utc + timedelta(hours=1),
                )
                # Add part item if present
                if recipe["part_desc"]:
                    add_item(
                        db=session,
                        ticket=t,
                        item_type="part",
                        description=recipe["part_desc"],
                        price_charged=recipe["part_price"],
                        cost_price=recipe["part_cost"],
                        supplier_name=recipe["supplier"],
                        now=intake_utc + timedelta(hours=1),
                    )
                session.commit()

                # Fast forward lifecycle
                ready_utc = intake_utc + timedelta(days=random.randint(1, 2), hours=random.randint(1, 4))
                delivered_utc = ready_utc + timedelta(days=random.randint(1, 4), hours=random.randint(1, 3))

                transition_ticket(session, t, TicketStatus.IN_PROGRESS.value, now=intake_utc + timedelta(hours=2))
                transition_ticket(session, t, TicketStatus.READY_FOR_PICKUP.value, now=ready_utc)

                # Final payment
                items_total = recipe["labor"] + recipe["part_price"]
                rem = items_total - adv_amt
                if rem > 0:
                    split = random.random() < 0.25 and rem >= 1000
                    if split:
                        p1 = 500
                        p2 = rem - 500
                        add_payment(session, t, amount=p1, mode="cash", kind=PaymentKind.FINAL.value, now=delivered_utc)
                        add_payment(session, t, amount=p2, mode="upi", kind=PaymentKind.FINAL.value, now=delivered_utc)
                    else:
                        mode = random.choice(["cash", "upi", "card"])
                        add_payment(session, t, amount=rem, mode=mode, kind=PaymentKind.FINAL.value, now=delivered_utc)

                transition_ticket(
                    session,
                    t,
                    TicketStatus.DELIVERED.value,
                    confirm_pending_balance=True,
                    clear_passcode=True,
                    now=delivered_utc,
                )
                session.commit()

                repaired_pool.append(t)
                all_created_tickets.append(t)

            day_cursor += timedelta(days=1)

        print(f"Generated {len(repaired_pool)} historical delivered repairs.")

        # Special seed requirement: 4 declined (2 with diagnostic fee)
        for i in range(4):
            cust_name, cust_phone = random.choice(CUSTOMER_DATA)
            brand, model = random.choice(DEVICES)
            dt_utc = (utc_now() - timedelta(days=random.randint(10, 40)))
            t = create_ticket(
                db=session,
                customer_phone=cust_phone,
                customer_name=cust_name,
                device_brand=brand,
                device_model=model,
                reported_issue="Customer declined estimate for replacement",
                issue_category="Screen",
                now=dt_utc,
            )
            if i < 2:
                add_item(session, t, item_type="labor", description="Diagnostic fee", price_charged=150, now=dt_utc + timedelta(hours=1))
                add_payment(session, t, amount=150, mode="cash", kind=PaymentKind.FINAL.value, now=dt_utc + timedelta(hours=2))

            transition_ticket(session, t, TicketStatus.DECLINED.value, note="Customer declined repair", now=dt_utc + timedelta(hours=2))
            transition_ticket(session, t, TicketStatus.DELIVERED.value, confirm_pending_balance=True, now=dt_utc + timedelta(hours=3))
            session.commit()

        # Special seed requirement: 3 unrepairable
        for i in range(3):
            cust_name, cust_phone = random.choice(CUSTOMER_DATA)
            brand, model = random.choice(DEVICES)
            dt_utc = (utc_now() - timedelta(days=random.randint(5, 30)))
            t = create_ticket(
                db=session,
                customer_phone=cust_phone,
                customer_name=cust_name,
                device_brand=brand,
                device_model=model,
                reported_issue="Severe PCB motherboard corrosion",
                issue_category="Motherboard",
                now=dt_utc,
            )
            transition_ticket(session, t, TicketStatus.UNREPAIRABLE.value, note="Motherboard layered damage beyond repair", now=dt_utc + timedelta(hours=3))
            transition_ticket(session, t, TicketStatus.DELIVERED.value, confirm_pending_balance=True, now=dt_utc + timedelta(hours=4))
            session.commit()

        # Special seed requirement: 3 warranty return tickets linked to repaired parents
        if repaired_pool:
            p1 = repaired_pool[0]
            p2 = repaired_pool[1]
            p3 = repaired_pool[2]
            create_ticket(
                db=session,
                customer_phone=p1.customer.phone,
                customer_name=p1.customer.name,
                device_brand=p1.device_brand,
                device_model=p1.device_model,
                reported_issue="Display touch issue reappeared under warranty",
                issue_category="Screen",
                parent_ticket_id=p1.id,
                now=p1.delivered_at + timedelta(days=5),
            )
            create_ticket(
                db=session,
                customer_phone=p2.customer.phone,
                customer_name=p2.customer.name,
                device_brand=p2.device_brand,
                device_model=p2.device_model,
                reported_issue="Battery draining again",
                issue_category="Battery",
                parent_ticket_id=p2.id,
                now=p2.delivered_at + timedelta(days=10),
            )
            create_ticket(
                db=session,
                customer_phone=p3.customer.phone,
                customer_name=p3.customer.name,
                device_brand=p3.device_brand,
                device_model=p3.device_model,
                reported_issue="Charging stopped working",
                issue_category="Charging port",
                parent_ticket_id=p3.id,
                now=p3.delivered_at + timedelta(days=12),
            )
            session.commit()

        # Special seed requirement: 2 refunds
        if len(repaired_pool) >= 5:
            t_ref1 = repaired_pool[3]
            t_ref2 = repaired_pool[4]
            add_payment(session, t_ref1, amount=200, mode="cash", kind=PaymentKind.REFUND.value, note="Goodwill refund for delay", now=t_ref1.delivered_at + timedelta(days=1))
            add_payment(session, t_ref2, amount=150, mode="upi", kind=PaymentKind.REFUND.value, note="Partial refund for minor scratch", now=t_ref2.delivered_at + timedelta(days=1))
            session.commit()

        # Special seed requirement: 1 ticket delivered with pending balance (audited)
        t_pend = create_ticket(
            db=session,
            customer_phone="9821889012",
            customer_name="Swati Bhatt",
            device_brand="Samsung",
            device_model="Galaxy A32",
            reported_issue="Display replacement done",
            issue_category="Screen",
            now=utc_now() - timedelta(days=4),
        )
        add_item(session, t_pend, item_type="labor", description="Display repair", price_charged=2500, now=utc_now() - timedelta(days=4))
        add_payment(session, t_pend, amount=1500, mode="cash", kind=PaymentKind.ADVANCE.value, now=utc_now() - timedelta(days=4))
        transition_ticket(session, t_pend, TicketStatus.IN_PROGRESS.value, now=utc_now() - timedelta(days=3))
        transition_ticket(session, t_pend, TicketStatus.READY_FOR_PICKUP.value, now=utc_now() - timedelta(days=2))
        transition_ticket(session, t_pend, TicketStatus.DELIVERED.value, confirm_pending_balance=True, note="Delivered with pending balance of ₹1,000", now=utc_now() - timedelta(days=1))
        session.commit()

        # Special seed requirement: 1 soft-deleted payment and 1 soft-deleted ticket
        t_del = create_ticket(
            db=session,
            customer_phone="9821990123",
            customer_name="Nitin Saxena",
            device_brand="Oppo",
            device_model="F19 Pro",
            reported_issue="Duplicate intake entry by mistake",
            issue_category="Other",
            now=utc_now() - timedelta(days=10),
        )
        delete_ticket(session, t_del, reason="Duplicate ticket entered by accident", owner_pin="1234", now=utc_now() - timedelta(days=9))
        session.commit()

        t_paydel = repaired_pool[5]
        dummy_pay = add_payment(session, t_paydel, amount=500, mode="cash", kind=PaymentKind.FINAL.value, note="Accidental entry", confirm_overpay=True, now=utc_now() - timedelta(days=1))
        delete_payment(session, dummy_pay, reason="Wrong ticket selected during billing", owner_pin="1234", now=utc_now() - timedelta(days=1))
        session.commit()

        # Special seed requirement: about 8 active tickets across statuses
        now_utc = utc_now()

        # Stale active ticket 1: received 12 days ago, still received
        create_ticket(
            db=session,
            customer_phone="9820112345",
            customer_name="Aarav Sharma",
            device_brand="Apple",
            device_model="iPhone 11",
            reported_issue="FaceID not working after drop",
            issue_category="Camera",
            now=now_utc - timedelta(days=12),
        )

        # Stale active ticket 2: in_progress for 9 days
        t_act2 = create_ticket(
            db=session,
            customer_phone="9820223456",
            customer_name="Priya Patel",
            device_brand="OnePlus",
            device_model="Nord 2",
            reported_issue="Motherboard shorting issue",
            issue_category="Motherboard",
            now=now_utc - timedelta(days=14),
        )
        transition_ticket(session, t_act2, TicketStatus.IN_PROGRESS.value, note="Waiting on complex IC chip soldering", now=now_utc - timedelta(days=9))

        # Active awaiting_approval
        t_act3 = create_ticket(
            db=session,
            customer_phone="9820334567",
            customer_name="Rohan Verma",
            device_brand="Vivo",
            device_model="V21",
            reported_issue="Back camera glass cracked",
            issue_category="Camera",
            estimate_amount=1200,
            now=now_utc - timedelta(days=2),
        )
        transition_ticket(session, t_act3, TicketStatus.AWAITING_APPROVAL.value, note="Estimate communicated to customer", now=now_utc - timedelta(days=1))

        # Active awaiting_parts
        t_act4 = create_ticket(
            db=session,
            customer_phone="9820445678",
            customer_name="Sneha Kulkarni",
            device_brand="Realme",
            device_model="9 Pro",
            reported_issue="Charging flex burnt",
            issue_category="Charging port",
            now=now_utc - timedelta(days=3),
        )
        transition_ticket(session, t_act4, TicketStatus.IN_PROGRESS.value, now=now_utc - timedelta(days=2))
        transition_ticket(session, t_act4, TicketStatus.AWAITING_PARTS.value, note="Special flex board ordered from Delhi", now=now_utc - timedelta(days=1))

        # Active in_progress (recent)
        t_act5 = create_ticket(
            db=session,
            customer_phone="9820556789",
            customer_name="Vikram Singh",
            device_brand="Redmi",
            device_model="Note 12",
            reported_issue="Screen flickering",
            issue_category="Screen",
            advance_amount=500,
            advance_mode="cash",
            now=now_utc - timedelta(days=1),
        )
        add_item(session, t_act5, item_type="labor", description="Screen diagnostic", price_charged=300, now=now_utc - timedelta(hours=10))
        transition_ticket(session, t_act5, TicketStatus.IN_PROGRESS.value, now=now_utc - timedelta(hours=8))

        # 3 Ready for pickup tickets:
        # Ready ticket 1: ready 10 days ago (oldest)
        t_rdy1 = create_ticket(
            db=session,
            customer_phone="9820667890",
            customer_name="Ananya Iyer",
            device_brand="Samsung",
            device_model="Galaxy S21",
            reported_issue="Battery replacement",
            issue_category="Battery",
            now=now_utc - timedelta(days=12),
        )
        add_item(session, t_rdy1, item_type="labor", description="Labor", price_charged=400, now=now_utc - timedelta(days=11))
        add_item(session, t_rdy1, item_type="part", description="S21 Battery", price_charged=1800, cost_price=1200, supplier_name="PowerTech", now=now_utc - timedelta(days=11))
        transition_ticket(session, t_rdy1, TicketStatus.IN_PROGRESS.value, now=now_utc - timedelta(days=11))
        transition_ticket(session, t_rdy1, TicketStatus.READY_FOR_PICKUP.value, now=now_utc - timedelta(days=10))

        # Ready ticket 2: ready 4 days ago
        t_rdy2 = create_ticket(
            db=session,
            customer_phone="9820778901",
            customer_name="Rahul Nair",
            device_brand="Motorola",
            device_model="G52",
            reported_issue="Charging port replaced",
            issue_category="Charging port",
            now=now_utc - timedelta(days=5),
        )
        add_item(session, t_rdy2, item_type="labor", description="Labor", price_charged=350, now=now_utc - timedelta(days=4))
        transition_ticket(session, t_rdy2, TicketStatus.IN_PROGRESS.value, now=now_utc - timedelta(days=4))
        transition_ticket(session, t_rdy2, TicketStatus.READY_FOR_PICKUP.value, now=now_utc - timedelta(days=4))

        # Ready ticket 3: ready 1 day ago
        t_rdy3 = create_ticket(
            db=session,
            customer_phone="9820889012",
            customer_name="Pooja Gupta",
            device_brand="Apple",
            device_model="iPhone 12",
            reported_issue="Ear speaker cleaning & mesh replacement",
            issue_category="Speaker/Mic",
            now=now_utc - timedelta(days=2),
        )
        add_item(session, t_rdy3, item_type="labor", description="Labor", price_charged=500, now=now_utc - timedelta(days=1))
        transition_ticket(session, t_rdy3, TicketStatus.IN_PROGRESS.value, now=now_utc - timedelta(days=1))
        transition_ticket(session, t_rdy3, TicketStatus.READY_FOR_PICKUP.value, now=now_utc - timedelta(days=1))

        session.commit()

        # Daily cash closings for past 30 days
        print("Closing past cash days with small realistic variances...")
        closings_start = today - timedelta(days=30)
        curr_d = closings_start
        last_counted = 3500

        while curr_d < today:
            variance_choice = random.choices([0, -50, 50, -100, 20], weights=[70, 10, 10, 5, 5])[0]
            from app.services.cash_close import compute_day_cash_summary
            summary = compute_day_cash_summary(session, curr_d, opening_cash=last_counted)
            expected = summary["expected_cash"]
            counted = max(0, expected + variance_choice)
            note = f"Variance of ₹{variance_choice}" if variance_choice != 0 else None

            close_cash_day(
                db=session,
                target_date=curr_d,
                opening_cash=last_counted,
                counted_cash=counted,
                note=note,
                now=datetime.combine(curr_d, datetime.min.time(), tzinfo=IST).astimezone(UTC) + timedelta(hours=21),
            )
            session.commit()
            last_counted = counted
            curr_d += timedelta(days=1)

        total_tickets = session.query(func.count(Ticket.id)).scalar()
        print("=" * 60)
        print("SEED COMPLETED SUCCESSFULLY")
        print(f"Total tickets seeded: {total_tickets}")
        print("Demo credentials:")
        print("  Password: demo12345")
        print("  Owner PIN: 1234")
        print("=" * 60)

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Seed Mobile Repair Shop database")
    parser.add_argument("--reset", action="store_true", help="Wipe and recreate seed data")
    args = parser.parse_args()
    seed_database(reset=args.reset)


if __name__ == "__main__":
    main()
