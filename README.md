# 📱 Mobile Repair Shop Management System

A high-performance, local-first management system designed for Indian mobile repair shops. Built with **FastAPI**, **SQLite WAL**, **Alembic**, **Jinja2**, **HTMX 2.0.3**, and **Tailwind CSS**.

---

## 🚀 Quick Start (Development & Local Demo)

The project is managed exclusively with [`uv`](https://github.com/astral-sh/uv).

### 1. Prerequisites
- Python 3.12+
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`)

### 2. Setup Environment & Install Dependencies
```bash
# Clone and enter directory
cd service

# Create virtual environment and install all dependencies
uv sync
```

### 3. Initialize Database & Seed Demo Data
```bash
# Apply database migrations
uv run alembic upgrade head

# Seed 90 days of realistic shop data (~105 tickets, customers, cash closings)
uv run python -m scripts.seed --reset
```

### 4. Start the Application
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🔑 Demo Credentials

| Role / Feature | Credential | Description |
|---|---|---|
| **Login Password** | `demo12345` | Main shop session access (12h session) |
| **Owner PIN** | `1234` | Required for destructive actions, cash reopening, reports, and editing delivered tickets |

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
2. Navigate to `data/` and copy the desired backup file from `backups/shop-YYYYMMDD-HHMMSS.db` over `data/shop.db`.
3. Verify integrity:
   ```bash
   sqlite3 data/shop.db "PRAGMA integrity_check;"
   ```
4. Start the application server.

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
