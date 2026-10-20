# 📱 Mobile Repair Shop Management System

A high-performance, local-first management system designed for Indian mobile repair shops. Built with **FastAPI**, **SQLite WAL**, **Alembic**, **Jinja2**, **HTMX 2.0.3**, and **Tailwind CSS**.

---

## Windows Shop Owner Setup (Fresh Shop)

Get the project folder from GitHub, then double-click **`setup_shop_pc.bat`**. The setup installs the required runtime and dependencies, prepares an empty database, and creates the Desktop shortcut **Amee Mobiles POS** plus a Windows sign-in startup shortcut. It does not seed sample tickets or import shop data.

Double-click **Amee Mobiles POS** and complete the first-run password and Owner PIN setup. The shop name is prefilled as **AMEE MOBILES**. The receipt terms and WhatsApp intake message are also preconfigured.

For transfer details and fresh-install file exclusions, see [LOCAL_SETUP_GUIDE.md](LOCAL_SETUP_GUIDE.md). Local databases, backups, and `.env` secrets are intentionally excluded from Git.

## Local Development

The project uses [`uv`](https://github.com/astral-sh/uv) and Python 3.12 or later.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

This creates a blank development database and opens the first-run setup page at **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. Shop-owner setup does not use the development seed scripts.

---

## 🌟 Key Features & Architectural Highlights

1. **Intake & Repair Queue**:
   - Customer phone auto-lookup (10-digit normalized format `98XXXXXXXX`).
   - Customer duplicate / return check before creating ticket.
   - Secure encrypted device passcode storage (Fernet symmetric key) with audited single-click reveal and auto-clear on delivery.
   - Advance payments (cash / UPI) recorded directly at intake.
   - Instant 80mm thermal receipt print preview and click-to-WhatsApp (`wa.me`) status message.

2. **Finite State Lifecycle & Delivery Gate**:
   - Strict 8-stage state machine: `received` ➔ `awaiting_approval` ➔ `in_progress` ➔ `awaiting_parts` ➔ `ready_for_pickup` ➔ `delivered` / `declined` / `unrepairable`.
   - **Delivery Gate**: Tickets cannot be marked `delivered` if there is a pending balance or excess payment without explicit confirmation.
   - Rework & warranty tracking: warranty returns link directly to parent tickets.

3. **Money & Line Item Billing**:
   - Integer paise/rupee arithmetic — zero floating-point discrepancies.
   - Indian currency formatting (`format_inr`): e.g., `₹1,23,456`.
   - Line items: Labor and Spare Parts (with cost price, supplier name, and live profit margin tracking).
   - Partial payments, split payments (Cash + UPI), and refunds (capped at net paid, requiring audited reasons).

4. **Daily Cash Reconciliation**:
   - Computes expected cash: `Opening Cash + Cash In - Cash Refunds`.
   - Tracks live cash drawer variance (`Counted Cash - Expected Cash`).
   - Nightly day-closing lock: prevents recording new payments into closed days without reopening.
   - Day reopening requires Owner PIN and mandatory reason.

5. **Analytics & Financial Dashboard**:
   - 16 core business metrics calculated strictly across IST boundaries (`Asia/Kolkata`).
   - Gross revenue, billed value, parts cost, gross profit margins, fix success rate, and pickup turnaround times.
   - Daily revenue breakdown charts powered by Chart.js.
   - Cash closing variance audit log.

6. **Customer History & Global Search**:
   - Sub-second search (< 100ms on 20,000 tickets) across Ticket #, Customer Name, Phone, IMEI/Serial, Device Brand, and Model.
   - Full customer timeline of past repairs, warranty badges, and lifetime spend.

7. **Data Migration & CSV/Excel Importer**:
   - Drag-and-drop CSV or XLSX file import.
   - Dynamic column mapper with dry-run preview before committing.

8. **Enterprise Durability & Security**:
   - SQLite WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;`).
   - Database triggers preventing hard `DELETE` operations on tickets, payments, items, and status history.
   - Append-only `audit_log` with SQLite trigger forbidding `UPDATE` and `DELETE`.
   - Automated nightly online backups using `sqlite3.backup()` with 30-day retention pruning.

9. **Spare Parts Inventory Management**:
   - In-stock spare parts catalog (displays, batteries, charging ports, backdoors, motherboards, etc.) with real-time quantities.
   - Cost price, selling price, and supplier tracking with stock adjustment history.
   - Automatic stock deduction when assigned to a repair ticket, and automatic replenishment when a stock-linked line item is deleted.

---

## 🧪 Testing Suite & Quality Verification

Run the full automated test suite:
```bash
# Run all tests
uv run pytest

# Run with service layer test coverage
uv run pytest --cov=app/services --cov-report=term-missing
```

### Verified Acceptance Criteria (AC1 - AC9):
- **AC1 (Zero Floating Point Errors)**: Integer rupee storage verified in `tests/test_golden_reports.py`.
- **AC2 (Search Benchmark)**: Automated test `tests/test_search_perf.py` generates 20,000 tickets in SQLite and verifies 10 random LIKE queries all execute well under 1,000ms.
- **AC3 (8x8 Transition Matrix)**: Exhaustive test `tests/test_lifecycle.py` validates all permitted and forbidden transitions.
- **AC4 (Split Billing & Delivery Gate)**: `tests/test_money.py` tests advance + UPI remainder flow and delivery balance gates.
- **AC5 (No Orphan Payments)**: Foreign key constraints and transaction atomicity verified in `tests/test_money.py`.
- **AC6 (Day Reopen PIN Audit)**: `tests/test_cash_close.py` verifies Owner PIN protection and audit logging.
- **AC7 (Soft Delete & Append-Only Audit)**: `tests/test_audit.py` verifies SQLite triggers reject DELETE on tickets and UPDATE/DELETE on audit log.
- **AC8 (Golden Dataset Invariants)**: `tests/test_golden_reports.py` matches all 16 metrics against the exact Section 14.3 hand-calculated dataset.
- **AC9 (Backup & Integrity Check)**: `tests/test_backups.py` validates `PRAGMA integrity_check` on online backups and 30-backup pruning.

---

## 🔒 Code Quality & Linter

```bash
uv run ruff check .
```

---

## 💾 Backups & Windows Task Scheduler

### Online Backups
Backups are created using SQLite's native online backup API (`sqlite3.backup()`), which executes safely while the database is actively receiving reads and writes.

To trigger a manual backup via CLI:
```bash
uv run python -c "from app.services.backup import create_backup; print(create_backup())"
```

### Setting Up Windows Task Scheduler (Nightly 02:00 AM IST)
To register a scheduled task on Windows:
```powershell
schtasks /create /tn "MobileRepairShop_NightlyBackup" /tr "powershell -Command \"cd C:\Users\admin\Desktop\service; uv run python -c 'from app.services.backup import create_backup; create_backup()'\"" /sc daily /st 02:00
```

### Disaster Recovery / Database Restore
To restore from a backup:
1. Stop the application server (`uvicorn`).
2. Remove any existing WAL and SHM sidecar files to prevent frame replay mismatch:
   ```bash
   rm -f data/shop.db-wal data/shop.db-shm
   ```
   *(On Windows PowerShell: `Remove-Item -Force data\shop.db-wal, data\shop.db-shm -ErrorAction SilentlyContinue`)*
3. Copy the desired backup file over `data/shop.db`:
   ```bash
   cp backups/shop-YYYYMMDD-HHMMSS.db data/shop.db
   ```
4. Verify database integrity:
   ```bash
   sqlite3 data/shop.db "PRAGMA integrity_check;"
   ```
5. Start the application server.

*(Alternatively, use the safe Python restore helper: `uv run python -c "from pathlib import Path; from app.services.backup import restore_backup_file; restore_backup_file(Path('backups/shop-YYYYMMDD-HHMMSS.db'))"`)*

---

## 🐳 Docker Deployment

A production-ready `Dockerfile` is included:

```bash
# Build Docker image
docker build -t mobile-repair-shop:latest .

# Run container with persistent data and backup volumes
docker run -d \
  -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/backups:/app/backups" \
  --name repair-shop \
  mobile-repair-shop:latest
```

Health check endpoint: `GET http://localhost:8000/healthz` (returns `{"status": "ok", "db": "ok"}`).
