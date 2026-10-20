"""Dev-only seed script for Mobile Repair Shop UI/UX development.

Creates ~25 realistic tickets across all statuses with varied aging and balances.
Guarded by APP_ENV != production check and --dev CLI flag.
"""

import argparse
from pathlib import Path
import sys
from datetime import timedelta

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

from app.config import Settings
from app.db import SessionLocal
from app.models.customer import Customer
from app.models.enums import PaymentKind, PaymentMode, TicketStatus
from app.models.payment import Payment
from app.models.settings import Settings as SettingsModel
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.security import hash_secret
from app.services.items import add_item
from app.services.payments import add_payment
from app.services.status import transition_ticket
from app.services.tickets import create_ticket
from app.timeutil import utc_now


def seed_dev_data():
    cfg = Settings()
    # Production guard
    if cfg.is_production or cfg.APP_ENV.lower() == "production":
        print("ERROR: Dev seed cannot be executed in production environment!", file=sys.stderr)
        sys.exit(1)

    session = SessionLocal()
    try:
        # Ensure default settings exist (preserve existing admin password and pin if present)
        stg = session.query(SettingsModel).filter_by(id=1).first()
        if not stg:
            stg = SettingsModel(
                id=1,
                shop_name="AMEE Mobiles",
                admin_password_hash=hash_secret("12345"),
                owner_pin_hash=hash_secret("12345"),
                ticket_no_prefix="AMEE",
                next_ticket_seq=101,
            )
            session.add(stg)
            session.flush()
        else:
            stg.admin_password_hash = hash_secret("12345")
            stg.owner_pin_hash = hash_secret("12345")

        # Clean existing tickets and related records to ensure a clean ~25 ticket dataset
        print("Clearing existing tickets, items, payments, status histories for clean dev seed...")
        session.execute(delete(Payment))
        session.execute(delete(TicketItem))
        session.execute(delete(StatusHistory))
        session.execute(delete(Ticket))
        session.commit()

        # Reset next_ticket_seq to 101 for clean numbers
        stg.next_ticket_seq = 101
        session.commit()

        now = utc_now()

        # 26 tickets across all statuses
        # 1. Received (3 tickets)
        print("Seeding Received tickets (3)...")
        t_rec1 = create_ticket(
            db=session,
            customer_phone="9820112345",
            customer_name="Aarav Sharma",
            device_brand="Samsung",
            device_model="Galaxy M31",
            reported_issue="Display flickering and touch unresponsive at bottom",
            issue_category="Screen",
            color="Ocean Blue",
            estimate_amount=2500,
            now=now - timedelta(hours=2),
        )

        t_rec2 = create_ticket(
            db=session,
            customer_phone="9820223456",
            customer_name="Priya Patel",
            device_brand="Apple",
            device_model="iPhone 13",
            reported_issue="Back camera glass cracked, lens blurry",
            issue_category="Camera",
            color="Midnight Black",
            estimate_amount=3200,
            now=now - timedelta(days=1, hours=3),
        )

        t_rec3 = create_ticket(
            db=session,
            customer_phone="9820334567",
            customer_name="Rohan Verma",
            device_brand="OnePlus",
            device_model="Nord CE 2",
            reported_issue="No sound from earpiece during normal calls",
            issue_category="Speaker/Mic",
            color="Bahamas Blue",
            estimate_amount=800,
            now=now - timedelta(days=2),
        )

        # 2. Awaiting Approval (4 tickets - with 2 aging > 2 days)
        print("Seeding Awaiting Approval tickets (4)...")
        t_app1 = create_ticket(
            db=session,
            customer_phone="9820445678",
            customer_name="Sneha Kulkarni",
            device_brand="Realme",
            device_model="9 Pro",
            reported_issue="Liquid damage; power IC short circuit diagnosed",
            issue_category="Motherboard",
            color="Aurora Green",
            estimate_amount=3500,
            now=now - timedelta(days=4),  # aging 4 days! (>2d warning)
        )
        add_item(session, t_app1, item_type="labor", description="Motherboard IC reballing", price_charged=1500, now=now - timedelta(days=4))
        add_item(session, t_app1, item_type="part", description="Power IC Chip", price_charged=2000, cost_price=1200, supplier_name="ChipMaster Spares", now=now - timedelta(days=4))
        transition_ticket(session, t_app1, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(days=4))

        t_app2 = create_ticket(
            db=session,
            customer_phone="9820556789",
            customer_name="Vikram Singh",
            device_brand="Vivo",
            device_model="V21",
            reported_issue="OLED screen broken + frame bent, estimate sent to customer",
            issue_category="Screen",
            color="Sunset Dazzle",
            estimate_amount=4200,
            now=now - timedelta(days=3),  # aging 3 days! (>2d warning)
        )
        add_item(session, t_app2, item_type="part", description="AMOLED Display Panel + Frame", price_charged=3600, cost_price=2700, supplier_name="Metro Screen Wholesalers", now=now - timedelta(days=3))
        add_item(session, t_app2, item_type="labor", description="Full frame housing transfer", price_charged=600, now=now - timedelta(days=3))
        transition_ticket(session, t_app2, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(days=3))

        t_app3 = create_ticket(
            db=session,
            customer_phone="9820667890",
            customer_name="Ananya Iyer",
            device_brand="Redmi",
            device_model="Note 12",
            reported_issue="Swollen battery pushing back cover open",
            issue_category="Battery",
            color="Frosted Green",
            estimate_amount=1600,
            now=now - timedelta(days=1),
        )
        add_item(session, t_app3, item_type="part", description="Original BN50 Battery", price_charged=1200, cost_price=800, supplier_name="PowerTech Spares", now=now - timedelta(days=1))
        add_item(session, t_app3, item_type="labor", description="Battery replacement & adhesive kit", price_charged=400, now=now - timedelta(days=1))
        transition_ticket(session, t_app3, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(days=1))

        t_app4 = create_ticket(
            db=session,
            customer_phone="9820778901",
            customer_name="Rahul Nair",
            device_brand="Samsung",
            device_model="Galaxy A32",
            reported_issue="Sub-board charging connector broken, mic not working",
            issue_category="Charging port",
            color="Awesome Violet",
            estimate_amount=1100,
            now=now - timedelta(hours=8),
        )
        add_item(session, t_app4, item_type="part", description="Charging Sub-board module", price_charged=750, cost_price=450, supplier_name="PowerTech Spares", now=now - timedelta(hours=6))
        add_item(session, t_app4, item_type="labor", description="Soldering & installation", price_charged=350, now=now - timedelta(hours=6))
        transition_ticket(session, t_app4, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(hours=6))

        # 3. In Progress (4 tickets)
        print("Seeding In Progress tickets (4)...")
        t_prog1 = create_ticket(
            db=session,
            customer_phone="9820889012",
            customer_name="Pooja Gupta",
            device_brand="Apple",
            device_model="iPhone 11",
            reported_issue="Battery replacement & speaker mesh cleaning",
            issue_category="Battery",
            color="White",
            estimate_amount=2200,
            now=now - timedelta(days=2),
        )
        add_item(session, t_prog1, item_type="part", description="High Capacity Battery (OEM)", price_charged=1700, cost_price=1100, supplier_name="PowerTech Spares", now=now - timedelta(days=2))
        add_item(session, t_prog1, item_type="labor", description="Installation & battery calibration", price_charged=500, now=now - timedelta(days=2))
        transition_ticket(session, t_prog1, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=1))

        t_prog2 = create_ticket(
            db=session,
            customer_phone="9820990123",
            customer_name="Amit Deshmukh",
            device_brand="Motorola",
            device_model="G52",
            reported_issue="Cracked front glass, digitizer working fine",
            issue_category="Screen",
            color="Charcoal Grey",
            estimate_amount=2400,
            now=now - timedelta(days=1),
        )
        add_item(session, t_prog2, item_type="part", description="FHD+ AMOLED Screen Assembly", price_charged=1900, cost_price=1350, supplier_name="Metro Screen Wholesalers", now=now - timedelta(days=1))
        add_item(session, t_prog2, item_type="labor", description="Display replacement service", price_charged=500, now=now - timedelta(days=1))
        transition_ticket(session, t_prog2, TicketStatus.IN_PROGRESS.value, now=now - timedelta(hours=14))

        t_prog3 = create_ticket(
            db=session,
            customer_phone="9821001234",
            customer_name="Neha Joshi",
            device_brand="Poco",
            device_model="X4 Pro",
            reported_issue="Phone reboots continuously when WiFi turned on",
            issue_category="Software",
            color="Laser Blue",
            estimate_amount=900,
            now=now - timedelta(days=1),
        )
        add_item(session, t_prog3, item_type="labor", description="Firmware flash & diagnostic testing", price_charged=900, now=now - timedelta(hours=18))
        transition_ticket(session, t_prog3, TicketStatus.IN_PROGRESS.value, now=now - timedelta(hours=12))

        t_prog4 = create_ticket(
            db=session,
            customer_phone="9821112345",
            customer_name="Suresh Reddy",
            device_brand="Oppo",
            device_model="F19 Pro",
            reported_issue="Volume buttons jammed, power button stiff",
            issue_category="Body/Housing",
            color="Fluid Black",
            estimate_amount=700,
            now=now - timedelta(hours=5),
        )
        add_item(session, t_prog4, item_type="part", description="Volume & Power Flex Cable", price_charged=400, cost_price=220, supplier_name="Apex Mobile Spares", now=now - timedelta(hours=4))
        add_item(session, t_prog4, item_type="labor", description="Flex cable installation", price_charged=300, now=now - timedelta(hours=4))
        transition_ticket(session, t_prog4, TicketStatus.IN_PROGRESS.value, now=now - timedelta(hours=3))

        # 4. Awaiting Parts (3 tickets)
        print("Seeding Awaiting Parts tickets (3)...")
        t_part1 = create_ticket(
            db=session,
            customer_phone="9821223456",
            customer_name="Kavita Rao",
            device_brand="OnePlus",
            device_model="Nord 2",
            reported_issue="Display shattered after vehicle run-over; awaiting genuine screen",
            issue_category="Screen",
            color="Gray Sierra",
            estimate_amount=4800,
            now=now - timedelta(days=5),
        )
        add_item(session, t_part1, item_type="labor", description="Screen & frame labor", price_charged=700, now=now - timedelta(days=5))
        transition_ticket(session, t_part1, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=4))
        transition_ticket(session, t_part1, TicketStatus.AWAITING_PARTS.value, now=now - timedelta(days=3))

        t_part2 = create_ticket(
            db=session,
            customer_phone="9821334567",
            customer_name="Deepak Mehta",
            device_brand="Samsung",
            device_model="Galaxy S21",
            reported_issue="Camera module sensor error on 3x telephoto",
            issue_category="Camera",
            color="Phantom Gray",
            estimate_amount=3800,
            now=now - timedelta(days=3),
        )
        add_item(session, t_part2, item_type="labor", description="Camera module replacement labor", price_charged=800, now=now - timedelta(days=3))
        transition_ticket(session, t_part2, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=2))
        transition_ticket(session, t_part2, TicketStatus.AWAITING_PARTS.value, now=now - timedelta(days=2))

        t_part3 = create_ticket(
            db=session,
            customer_phone="9821445678",
            customer_name="Sunita Pillai",
            device_brand="Realme",
            device_model="Narzo 50",
            reported_issue="Charging IC fried by faulty car charger; part ordered",
            issue_category="Motherboard",
            color="Speed Blue",
            estimate_amount=1800,
            now=now - timedelta(days=2),
        )
        add_item(session, t_part3, item_type="labor", description="SMD IC soldering labor", price_charged=1000, now=now - timedelta(days=2))
        transition_ticket(session, t_part3, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=1))
        transition_ticket(session, t_part3, TicketStatus.AWAITING_PARTS.value, now=now - timedelta(days=1))

        # 5. Ready for Pickup (5 tickets - 2 aging 7+ days, diverse balances)
        print("Seeding Ready for Pickup tickets (5, including 2 aging 7+ days)...")
        # Ready 1: Ready 11 days ago! (Stale >7d, balance due ₹2,200)
        t_rdy1 = create_ticket(
            db=session,
            customer_phone="9821556789",
            customer_name="Manoj Kumar",
            device_brand="Apple",
            device_model="iPhone 12",
            reported_issue="OLED Screen replacement",
            issue_category="Screen",
            color="Blue",
            estimate_amount=5200,
            now=now - timedelta(days=13),
        )
        add_item(session, t_rdy1, item_type="part", description="OLED Screen Assembly (Hard OLED)", price_charged=4400, cost_price=3300, supplier_name="Metro Screen Wholesalers", now=now - timedelta(days=12))
        add_item(session, t_rdy1, item_type="labor", description="Installation & TrueTone transfer", price_charged=800, now=now - timedelta(days=12))
        # Advance payment of 3000 paid at intake
        add_payment(session, t_rdy1, amount=3000, mode=PaymentMode.UPI.value, kind=PaymentKind.ADVANCE.value, now=now - timedelta(days=13))
        transition_ticket(session, t_rdy1, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=12))
        transition_ticket(session, t_rdy1, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=11))

        # Ready 2: Ready 8 days ago! (Stale >7d, full balance due ₹1,400)
        t_rdy2 = create_ticket(
            db=session,
            customer_phone="9821667890",
            customer_name="Divya Agarwal",
            device_brand="Redmi",
            device_model="Note 11",
            reported_issue="Charging port replaced & speaker cleaned",
            issue_category="Charging port",
            color="Star Blue",
            estimate_amount=1400,
            now=now - timedelta(days=9),
        )
        add_item(session, t_rdy2, item_type="part", description="Charging Sub-board (Original)", price_charged=900, cost_price=550, supplier_name="PowerTech Spares", now=now - timedelta(days=9))
        add_item(session, t_rdy2, item_type="labor", description="Sub-board replacement & seal", price_charged=500, now=now - timedelta(days=9))
        transition_ticket(session, t_rdy2, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=8))
        transition_ticket(session, t_rdy2, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=8))

        # Ready 3: Ready 3 days ago (Balance due ₹600)
        t_rdy3 = create_ticket(
            db=session,
            customer_phone="9821778901",
            customer_name="Rajesh Chauhan",
            device_brand="Samsung",
            device_model="Galaxy M31",
            reported_issue="Battery replacement 6000mAh",
            issue_category="Battery",
            color="Space Black",
            estimate_amount=1600,
            now=now - timedelta(days=4),
        )
        add_item(session, t_rdy3, item_type="part", description="Samsung Original M31 Battery", price_charged=1200, cost_price=850, supplier_name="PowerTech Spares", now=now - timedelta(days=4))
        add_item(session, t_rdy3, item_type="labor", description="Battery replacement labor", price_charged=400, now=now - timedelta(days=4))
        add_payment(session, t_rdy3, amount=1000, mode=PaymentMode.CASH.value, kind=PaymentKind.ADVANCE.value, now=now - timedelta(days=4))
        transition_ticket(session, t_rdy3, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=3))
        transition_ticket(session, t_rdy3, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=3))

        # Ready 4: Ready 1 day ago (Fully paid ₹2,100, Balance due ₹0)
        t_rdy4 = create_ticket(
            db=session,
            customer_phone="9821889012",
            customer_name="Swati Bhatt",
            device_brand="Vivo",
            device_model="Y20",
            reported_issue="Folder/Display combo changed",
            issue_category="Screen",
            color="Nebula Blue",
            estimate_amount=2100,
            now=now - timedelta(days=2),
        )
        add_item(session, t_rdy4, item_type="part", description="Y20 Display Combo", price_charged=1600, cost_price=1100, supplier_name="Metro Screen Wholesalers", now=now - timedelta(days=2))
        add_item(session, t_rdy4, item_type="labor", description="Fitting labor", price_charged=500, now=now - timedelta(days=2))
        add_payment(session, t_rdy4, amount=2100, mode=PaymentMode.UPI.value, kind=PaymentKind.ADVANCE.value, now=now - timedelta(days=2))
        transition_ticket(session, t_rdy4, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=1))
        transition_ticket(session, t_rdy4, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=1))

        # Ready 5: Ready today (Balance due ₹850)
        t_rdy5 = create_ticket(
            db=session,
            customer_phone="9821990123",
            customer_name="Nitin Saxena",
            device_brand="Redmi",
            device_model="Note 10",
            reported_issue="Loudspeaker low volume & distorted",
            issue_category="Speaker/Mic",
            color="Shadow Black",
            estimate_amount=850,
            now=now - timedelta(hours=6),
        )
        add_item(session, t_rdy5, item_type="part", description="Ringer/Loudspeaker Module", price_charged=500, cost_price=280, supplier_name="PowerTech Spares", now=now - timedelta(hours=5))
        add_item(session, t_rdy5, item_type="labor", description="Speaker replacement", price_charged=350, now=now - timedelta(hours=5))
        transition_ticket(session, t_rdy5, TicketStatus.IN_PROGRESS.value, now=now - timedelta(hours=4))
        transition_ticket(session, t_rdy5, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(hours=1))

        # 6. Declined (To Hand Back) (2 tickets)
        print("Seeding Declined tickets (2)...")
        t_dec1 = create_ticket(
            db=session,
            customer_phone="9822001234",
            customer_name="Shilpa Menon",
            device_brand="Samsung",
            device_model="Galaxy S21",
            reported_issue="Customer declined display quote of ₹8,500; phone reassembled",
            issue_category="Screen",
            color="Phantom Violet",
            estimate_amount=8500,
            now=now - timedelta(days=4),
        )
        transition_ticket(session, t_dec1, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(days=3))
        transition_ticket(session, t_dec1, TicketStatus.DECLINED.value, now=now - timedelta(days=2))

        t_dec2 = create_ticket(
            db=session,
            customer_phone="9822112345",
            customer_name="Gaurav Mishra",
            device_brand="Apple",
            device_model="iPhone 13",
            reported_issue="Motherboard repair cost too high; customer buying new phone",
            issue_category="Motherboard",
            color="Midnight",
            estimate_amount=12000,
            now=now - timedelta(days=3),
        )
        transition_ticket(session, t_dec2, TicketStatus.AWAITING_APPROVAL.value, now=now - timedelta(days=2))
        transition_ticket(session, t_dec2, TicketStatus.DECLINED.value, now=now - timedelta(days=1))

        # 7. Unrepairable (To Hand Back) (2 tickets)
        print("Seeding Unrepairable tickets (2)...")
        t_unrep1 = create_ticket(
            db=session,
            customer_phone="9822223456",
            customer_name="Meera Kapoor",
            device_brand="Realme",
            device_model="9 Pro",
            reported_issue="Severe ocean saltwater corrosion; CPU and PMIC charred",
            issue_category="Water Damage",
            color="Sunrise Blue",
            estimate_amount=0,
            now=now - timedelta(days=6),
        )
        transition_ticket(session, t_unrep1, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=5))
        transition_ticket(session, t_unrep1, TicketStatus.UNREPAIRABLE.value, now=now - timedelta(days=4))

        t_unrep2 = create_ticket(
            db=session,
            customer_phone="9822334567",
            customer_name="Alok Pandey",
            device_brand="Poco",
            device_model="X4 Pro",
            reported_issue="Board cracked in half from bike accident; no trace continuity",
            issue_category="Motherboard",
            color="Laser Black",
            estimate_amount=0,
            now=now - timedelta(days=3),
        )
        transition_ticket(session, t_unrep2, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=2))
        transition_ticket(session, t_unrep2, TicketStatus.UNREPAIRABLE.value, now=now - timedelta(days=2))

        # 8. Delivered (Last 30 Days) (3 tickets)
        print("Seeding Delivered tickets (3)...")
        t_del1 = create_ticket(
            db=session,
            customer_phone="9822445678",
            customer_name="Ritu Choudhary",
            device_brand="Samsung",
            device_model="Galaxy A32",
            reported_issue="Charging sub-board replacement",
            issue_category="Charging port",
            color="Black",
            estimate_amount=950,
            now=now - timedelta(days=12),
        )
        add_item(session, t_del1, item_type="part", description="Charging Sub-board", price_charged=650, cost_price=380, supplier_name="PowerTech Spares", now=now - timedelta(days=12))
        add_item(session, t_del1, item_type="labor", description="Fitting labor", price_charged=300, now=now - timedelta(days=12))
        add_payment(session, t_del1, amount=950, mode=PaymentMode.CASH.value, kind=PaymentKind.FINAL.value, now=now - timedelta(days=10))
        transition_ticket(session, t_del1, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=11))
        transition_ticket(session, t_del1, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=10))
        transition_ticket(session, t_del1, TicketStatus.DELIVERED.value, now=now - timedelta(days=10))

        t_del2 = create_ticket(
            db=session,
            customer_phone="9822556789",
            customer_name="Kunal Shah",
            device_brand="OnePlus",
            device_model="Nord CE 2",
            reported_issue="Screen replacement (OLED original)",
            issue_category="Screen",
            color="Bahamas Blue",
            estimate_amount=4500,
            now=now - timedelta(days=8),
        )
        add_item(session, t_del2, item_type="part", description="Nord CE 2 Display", price_charged=3800, cost_price=2900, supplier_name="Metro Screen Wholesalers", now=now - timedelta(days=8))
        add_item(session, t_del2, item_type="labor", description="Screen fitting & glue cure", price_charged=700, now=now - timedelta(days=8))
        add_payment(session, t_del2, amount=4500, mode=PaymentMode.UPI.value, kind=PaymentKind.FINAL.value, now=now - timedelta(days=6))
        transition_ticket(session, t_del2, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=7))
        transition_ticket(session, t_del2, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=6))
        transition_ticket(session, t_del2, TicketStatus.DELIVERED.value, now=now - timedelta(days=5))

        t_del3 = create_ticket(
            db=session,
            customer_phone="9822667890",
            customer_name="Tarun Bose",
            device_brand="Apple",
            device_model="iPhone 11",
            reported_issue="Battery replacement",
            issue_category="Battery",
            color="Red",
            estimate_amount=1800,
            now=now - timedelta(days=3),
        )
        add_item(session, t_del3, item_type="part", description="iPhone 11 OEM Battery", price_charged=1400, cost_price=950, supplier_name="PowerTech Spares", now=now - timedelta(days=3))
        add_item(session, t_del3, item_type="labor", description="Battery replacement service", price_charged=400, now=now - timedelta(days=3))
        add_payment(session, t_del3, amount=1800, mode=PaymentMode.CASH.value, kind=PaymentKind.FINAL.value, now=now - timedelta(days=2))
        transition_ticket(session, t_del3, TicketStatus.IN_PROGRESS.value, now=now - timedelta(days=2))
        transition_ticket(session, t_del3, TicketStatus.READY_FOR_PICKUP.value, now=now - timedelta(days=1))
        transition_ticket(session, t_del3, TicketStatus.DELIVERED.value, now=now - timedelta(days=1))

        session.commit()
        total_tickets = session.query(Ticket).count()
        print("=" * 60)
        print("DEV SEED COMPLETED SUCCESSFULLY")
        print(f"Total tickets seeded: {total_tickets}")
        print("Distribution:")
        print("  - Received: 3")
        print("  - Awaiting Approval: 4 (2 aging > 2 days)")
        print("  - In Progress: 4")
        print("  - Awaiting Parts: 3")
        print("  - Ready for Pickup: 5 (2 aging > 7 days)")
        print("  - Declined: 2")
        print("  - Unrepairable: 2")
        print("  - Delivered: 3")
        print("=" * 60)

    except Exception as e:
        session.rollback()
        print(f"Error during dev seed: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Seed Mobile Repair Shop database with realistic dev data")
    parser.add_argument(
        "--dev",
        action="store_true",
        required=True,
        help="Dev flag required to confirm non-production execution",
    )
    args = parser.parse_args()
    if not args.dev:
        print("Error: --dev flag is strictly required to execute dev seed.", file=sys.stderr)
        sys.exit(1)

    seed_dev_data()


if __name__ == "__main__":
    main()
