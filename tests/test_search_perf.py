import os
import tempfile
import time

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.db import Base, set_sqlite_immediate_transaction, set_sqlite_pragmas
from app.services.search import search_tickets


def test_search_performance_20k_tickets():
    """AC2: Benchmark search performance on 20,000 tickets.

    Must respond within 1,000ms (1s) across phone, name, ticket_no, and IMEI.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", set_sqlite_pragmas)
    event.listen(engine, "begin", set_sqlite_immediate_transaction)

    Base.metadata.create_all(bind=engine)

    # Fast bulk insertion of 20,000 tickets and customers via raw connection in one transaction
    print("Generating 20,000 records for AC2 performance benchmark...")
    with engine.begin() as conn:
        # Insert 5,000 customers (avg 4 tickets per customer)
        cust_rows = [
            (i, f"98200{i:05d}", f"Customer {i}", "2026-10-10 10:00:00", "2026-10-10 10:00:00")
            for i in range(1, 5001)
        ]
        conn.execute(
            text("INSERT INTO customers (id, phone, name, created_at, updated_at) VALUES (:1, :2, :3, :4, :5)"),
            [{"1": r[0], "2": r[1], "3": r[2], "4": r[3], "5": r[4]} for r in cust_rows],
        )

        brands = ["Apple", "Samsung", "Xiaomi", "OnePlus", "Vivo", "Oppo"]
        models = ["iPhone 13", "Galaxy S22", "Redmi Note 11", "Nord 2", "V23", "F21"]

        ticket_rows = []
        for i in range(1, 20001):
            cust_id = ((i - 1) % 5000) + 1
            brand = brands[i % len(brands)]
            model = models[i % len(models)]
            ticket_rows.append({
                "1": i,
                "2": f"R-{1000 + i}",
                "3": cust_id,
                "4": brand,
                "5": model,
                "6": f"86450000{i:07d}",
                "7": "Broken screen and battery replacement",
                "8": "Screen",
                "9": "{}",
                "10": "in_progress",
                "11": "2026-10-10 10:00:00",
                "12": 30,
                "13": 0,
                "14": "2026-10-10 10:00:00",
                "15": "2026-10-10 10:00:00",
            })

        conn.execute(
            text("""
            INSERT INTO tickets (
                id, ticket_no, customer_id, device_brand, device_model,
                imei_or_serial, reported_issue, issue_category, intake_condition,
                status, received_at, warranty_days, is_deleted, created_at, updated_at
            ) VALUES (
                :1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12, :13, :14, :15
            )
            """),
            ticket_rows,
        )

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()

    test_queries = [
        "9820001234",     # Phone exact
        "Customer 2500",  # Name exact
        "R-15432",        # Ticket number exact
        "864500000012345", # IMEI exact
        "iPhone",         # Device brand
        "Galaxy S22",     # Device model
        "98200",          # Phone prefix
        "R-10",           # Ticket prefix
        "Cust",           # Name prefix
        "864500",         # IMEI prefix
    ]

    durations = []
    try:
        for q in test_queries:
            t0 = time.perf_counter()
            results = search_tickets(session, q, limit=50)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            durations.append(elapsed_ms)
            assert elapsed_ms < 1000.0, f"Query '{q}' took {elapsed_ms:.2f}ms, exceeded 1,000ms threshold!"
            assert len(results) > 0, f"Query '{q}' returned no results on 20k dataset"

        p95 = sorted(durations)[int(len(durations) * 0.95)]
        print(f"AC2 Search Performance on 20k rows: max={max(durations):.2f}ms, p95={p95:.2f}ms, min={min(durations):.2f}ms")
    finally:
        session.close()
        engine.dispose()
        try:
            os.remove(db_path)
        except OSError:
            pass
