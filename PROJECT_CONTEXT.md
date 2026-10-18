# PROJECT CONTEXT: Mobile Repair Shop Management System

> **Generated for External AI Reasoning & Collaboration**  
> **Source Base:** Verified against repository source files, migrations, configurations, and test suites.  
> **Secrets Notice:** No secrets, credentials, or production encryption keys are included.

---

## 1. Project Purpose & Main Functionality

A local-first, high-reliability web management system tailored for Indian mobile repair shops (single-shop or independent technicians). It manages the entire repair lifecycle from device intake to customer handover, warranty tracking, financial reconciliation, and inventory tracking.

### Core Capabilities:
- **Intake & Repair Queue:** Customer lookup by 10-digit mobile number, duplicate/repeat repair detection, Fernet-encrypted passcode storage with single-click reveal and audit logging, advance payment collection, 80mm thermal receipt printing, and click-to-WhatsApp (`wa.me`) customer messaging.
- **Strict Finite State Machine & Delivery Gate:** 8-stage repair lifecycle (`received` ➔ `awaiting_approval` ➔ `in_progress` ➔ `awaiting_parts` ➔ `ready_for_pickup` ➔ `delivered` / `declined` / `unrepairable`). Tickets cannot be closed as `delivered` with unpaid or excess balance without explicit confirmation.
- **Money & Line-Item Billing:** Integer rupee arithmetic across all calculations (zero floating-point errors). Supports split payments (Cash, UPI, Card), labor charges, spare parts pricing (cost vs selling price), supplier tracking, profit margins, and partial/capped refunds.
- **Daily Cash Drawer Reconciliation:** Tracks opening cash, net cash inflow, cash refunds, counted cash, and drawer variances with end-of-day closing locks. Reopening closed cash drawers requires Owner PIN validation with an audited reason.
- **Inventory & Spare Parts Management:** Parts catalog tracking quantities, cost prices, selling prices, supplier details, low-stock indicators, and automatic stock deduction when assigned to repair tickets.
- **Analytics & IST Financial Dashboard:** 16 core business metrics (gross revenue, billed value, parts cost, gross profit, repair success rate, average turnaround times) calculated strictly on Indian Standard Time (`Asia/Kolkata`, UTC+05:30) date boundaries.
- **Durability & Tamper Protection:** SQLite WAL mode with SQL triggers preventing hard `DELETE` operations on tickets, payments, items, and status history, plus an append-only `audit_log` with triggers blocking `UPDATE` and `DELETE`. Automated online backups with 30-day pruning.

---

## 2. Technology Stack & Dependencies

- **Language & Runtime:** Python 3.12+ (`>=3.12`)
- **Package & Environment Manager:** `uv` (`uv.lock`, `pyproject.toml`)
- **Web Framework:** FastAPI `>=0.143.0`, Starlette
- **Server:** Uvicorn `[standard]>=0.54.0`
- **Database & ORM:** SQLite in WAL mode, SQLAlchemy `>=2.1.4`, Alembic `>=1.20.0`
- **Frontend / UI:** Server-Side Rendered (SSR) Jinja2 `>=3.1.6`, HTMX 2.0.3, Tailwind CSS, Chart.js (via CDN / static assets)
- **Security & Cryptography:** `cryptography>=50.0.2` (Fernet symmetric encryption for passcodes), `argon2-cffi>=25.1.0` (password & PIN hashing), `itsdangerous>=2.2.0` (signed session cookies)
- **Utilities & Date/Time:** `pydantic-settings>=2.15.0`, `tzdata>=2026.5` (accurate IANA `Asia/Kolkata` timezones on Windows), `apscheduler>=3.11.3` (background backup scheduling), `openpyxl>=3.1.5` (Excel import), `qrcode>=8.2` (receipt QR codes), `python-multipart>=0.0.32`
- **Dev & Test Stack:** `pytest>=9.1.1`, `pytest-cov>=7.1.0`, `httpx>=0.28.1`, `ruff>=0.17.0`

---

## 3. Directory Structure

```text
service/
├── .env.example              # Template for environment configuration
├── alembic/                  # Database migration scripts
│   ├── env.py                # Alembic migration runner connected to Base metadata
│   └── versions/             # Migration versions (e.g. 99c02672819f_initial_schema.py)
├── alembic.ini               # Alembic configuration
├── app/                      # Main application package
│   ├── config.py             # Pydantic Settings and environment validation
│   ├── db.py                 # SQLite engine, WAL configuration, custom UTCDateTime, Base
│   ├── deps.py               # FastAPI dependencies (require_login, verify_csrf, require_pin_unlock)
│   ├── formatting.py         # Currency (format_inr), dates, and phone formatters
│   ├── main.py               # FastAPI application setup, middleware, error handlers, router mounting
│   ├── security.py           # Argon2 password/PIN hashing, Fernet encryption, signed cookie sessions
│   ├── templating.py         # Jinja2 environment configuration with custom filters
│   ├── timeutil.py           # IST timezone normalization (Asia/Kolkata), business dates, UTC conversions
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── audit_log.py      # Immutable audit trail model
│   │   ├── base.py           # Shared TimestampMixin (created_at, updated_at)
│   │   ├── cash_closing.py   # Daily cash drawer closing and reconciliation model
│   │   ├── customer.py       # Customer master record (normalized 10-digit phone)
│   │   ├── enums.py          # Enums: TicketStatus, Outcome, PaymentMode, PaymentKind, ItemType
│   │   ├── inventory.py      # InventoryItem model for spare parts stock
│   │   ├── payment.py        # Payment transactions (advance, partial, final, refund)
│   │   ├── settings.py       # Shop profile, PIN hashes, sequence numbers, templates
│   │   ├── status_history.py # Ticket status audit log
│   │   ├── ticket.py         # Core Ticket model with foreign keys to customer and parent ticket
│   │   └── ticket_item.py    # Line items (labor and parts) associated with tickets
│   ├── routers/              # HTTP Route Handlers (FastAPI)
│   │   ├── audit.py          # /audit - Read-only log viewer
│   │   ├── auth.py           # /login, /logout, /pin, /setup
│   │   ├── autocomplete.py   # /autocomplete - Brand, model, and issue category suggestions
│   │   ├── cash.py           # /cash - Daily cash closing and reopening flows
│   │   ├── customers.py      # /customers - Customer profile and repair history
│   │   ├── dashboard.py      # /dashboard - 16-metric analytics and period comparisons
│   │   ├── health.py         # /health - System health check
│   │   ├── importer.py       # /import - CSV/Excel ticket importer with column mapping
│   │   ├── inventory.py      # /inventory - Spare parts stock management
│   │   ├── items.py          # /tickets/{id}/items - Adding/deleting parts and labor
│   │   ├── payments.py       # /tickets/{id}/payments - Recording payments and refunds
│   │   ├── queue.py          # /queue - Grouped ticket status view
│   │   ├── search.py         # /search - Global sub-second ticket search
│   │   ├── settings.py       # /settings - Shop configuration and manual backup trigger
│   │   └── tickets.py        # /tickets - Intake, view, status transitions, thermal receipts
│   ├── services/             # Core Business Logic Layer
│   │   ├── audit.py          # record_audit helper
│   │   ├── backup.py         # SQLite online backup API (sqlite3.backup) and retention pruning
│   │   ├── cash_close.py     # Drawer calculations, locking, and PIN-audited reopen
│   │   ├── customers.py      # Customer deduplication and creation
│   │   ├── errors.py         # Custom exceptions (InvalidTransition, NeedsConfirmation)
│   │   ├── importer.py       # File parsing and batch ticket generation
│   │   ├── inventory.py      # Stock adjustment, reservation, and restocking logic
│   │   ├── items.py          # Ticket item mutations and price/margin calculations
│   │   ├── payments.py       # Balance verification, refund caps, payment creation
│   │   ├── receipts.py       # Thermal receipt generation (print CSS, QR codes)
│   │   ├── reports.py        # Exact 16-metric financial report engine for IST windows
│   │   ├── search.py         # Search querying across tickets, customers, and devices
│   │   ├── settings_service.py # Sequence generator and settings updater
│   │   ├── status.py         # 8x8 State Machine transition matrix and delivery checks
│   │   ├── tickets.py        # Ticket lifecycle management and intake orchestration
│   │   └── warranty.py       # Warranty validity checks and rework ticket linking
│   ├── static/               # CSS, JavaScript (HTMX), icons, and logos
│   └── templates/            # Jinja2 HTML templates & HTMX partials
├── backups/                  # Default directory for online SQLite backup files
├── data/                     # Default location for SQLite database (shop.db)
├── pyproject.toml            # Project definition, dependencies, pytest & ruff configs
├── README.md                 # Project introduction and quick-start guide
├── DECISIONS.md              # Architectural Decision Records (ADRs A-01 through A-30)
├── MASTER_SPEC.md            # Detailed system specifications and requirements
├── scripts/                  # Management scripts
│   ├── gen_key.py            # Generates Fernet and secret keys
│   └── seed.py               # Generates realistic 90-day demo dataset
└── tests/                    # Automated Pytest suite (46 comprehensive tests)
```

---

## 4. Application Architecture & Data Flow

```
[Browser Client] (HTML5 + HTMX + Tailwind)
       │
       ▼ HTTP Request
[Security Headers Middleware] (Nosniff, Deny Frame, Same-Origin)
       │
       ▼
[FastAPI Router Layer] (app/routers/*.py)
       │──> Dependency: require_login (Signed Session Cookie via itsdangerous)
       │──> Dependency: verify_csrf (Validates X-CSRF-Token or form csrf_token on mutating requests)
       │──> Dependency: require_pin_unlock (Sliding 15-min PIN session for protected areas)
       ▼
[Service Business Logic Layer] (app/services/*.py)
       │──> Validates state transitions (status.py 8x8 matrix)
       │──> Validates money calculations & refund limits (payments.py)
       │──> Enforces inventory availability & stock deduction (inventory.py)
       │──> Appends audit logs (audit.py)
       ▼
[SQLAlchemy ORM + SQLite WAL Engine] (app/db.py & app/models/*.py)
       │──> Custom UTCDateTime translates naive/aware datetimes to UTC ISO strings
       │──> PRAGMAs: journal_mode=WAL, busy_timeout=5000, foreign_keys=ON
       ▼
[SQLite Storage & Triggers] (data/shop.db)
       └── Triggers reject DELETE on tickets, payments, items, status_history; reject UPDATE/DELETE on audit_log
```

### Data Flow Lifecycle:
1. **Intake Flow:** Staff submits intake form ➔ `services.customers.get_or_create_customer` looks up phone ➔ Encrypts device passcode using Fernet (`services.tickets.create_ticket`) ➔ Increments ticket sequence in `settings` ➔ If advance payment given, records payment (`services.payments.add_payment`) ➔ Returns rendered thermal receipt view or redirects to ticket details.
2. **Transition Flow:** Staff triggers status change ➔ `services.status.transition_ticket` verifies `VALID_TRANSITIONS` ➔ If moving to `delivered`, verifies balance due is zero or confirms override ➔ Sets outcome (`repaired`, `declined`, `unrepairable`) and delivery timestamp ➔ Automatically logs event in `status_history` and `audit_log`.
3. **Daily Cash Closing Flow:** Staff views current cash metrics ➔ Drawer computes `opening_cash + cash_payments - cash_refunds` ➔ Staff inputs `counted_cash` ➔ System records `variance` and sets `is_closed=True`. Future cash payments on closed days are rejected unless reopened with Owner PIN and reason.

---

## 5. Important Modules & Responsibilities

| Module | Location | Responsibility |
|---|---|---|
| `app.config` | `app/config.py` | Validates environment variables with Pydantic; checks production secret lengths. |
| `app.db` | `app/db.py` | Sets up SQLite engine with WAL pragmas, thread checks, and custom `UTCDateTime` type decorator. |
| `app.security` | `app/security.py` | Password & PIN hashing (`argon2`), symmetric encryption (`Fernet`), session encoding (`itsdangerous`). |
| `app.timeutil` | `app/timeutil.py` | Timezone helper enforcing UTC storage while calculating day boundaries strictly in `Asia/Kolkata`. |
| `app.services.status` | `app/services/status.py` | Enforces the finite state machine and delivery gate rules. |
| `app.services.payments` | `app/services/payments.py` | Enforces non-negative payments, refund caps, and payment deletions. |
| `app.services.reports` | `app/services/reports.py` | Computes the 16 core business metrics across specified IST date windows. |
| `app.services.cash_close` | `app/services/cash_close.py` | Reconciles daily cash drawer amounts, locks closed days, and audits reopenings. |
| `app.services.backup` | `app/services/backup.py` | Executes non-blocking `sqlite3.backup()`, verifies integrity, and manages retention pruning. |

---

## 6. API Endpoints, Database Schema & Triggers

### Primary Endpoints:
- **Authentication & Setup:**
  - `GET /login`, `POST /login`, `POST /logout`
  - `GET /pin`, `POST /pin` (Unlocks protected actions for 15-minute sliding window)
  - `GET /setup`, `POST /setup` (Initial shop wizard setup)
- **Tickets & Queue:**
  - `GET /queue` (Grouped queue view)
  - `GET /tickets/new`, `POST /tickets/new` (Intake creation)
  - `GET /tickets/{id}` (Detail view with timeline, line items, and payments)
  - `POST /tickets/{id}/status` (Triggers state machine transition)
  - `POST /tickets/{id}/reveal-passcode` (Audited passcode decrypt)
  - `GET /tickets/{id}/receipt` (Thermal receipt preview)
  - `POST /tickets/{id}/warranty-return` (Creates child ticket linked to parent)
- **Billing & Items:**
  - `POST /tickets/{id}/items` (Add labor charge or spare part item)
  - `POST /tickets/{id}/items/{item_id}/delete` (Soft-delete line item; requires PIN if ticket delivered)
  - `POST /tickets/{id}/payments` (Record payment or refund)
- **Cash, Analytics, Inventory & Admin:**
  - `GET /cash`, `POST /cash/close`, `POST /cash/reopen`
  - `GET /dashboard` (Financial KPIs, turnaround, charts)
  - `GET /inventory`, `POST /inventory/add`, `POST /inventory/{id}/adjust`
  - `GET /audit` (Audit log viewer)
  - `GET /settings`, `POST /settings`, `POST /settings/backup-now`
  - `GET /search?q=...` (Global JSON/HTMX search)
  - `GET /health` (Liveness probe)

### Database Schema (8 Tables):
1. `settings`: Single-row config table (`shop_name`, `owner_pin_hash`, `admin_password_hash`, `ticket_no_prefix`, `next_ticket_seq`, templates).
2. `customers`: Customer directory (`name`, `phone` [unique 10 digits], `notes`).
3. `tickets`: Repair tickets (`ticket_no` [unique], `customer_id`, `device_brand`, `device_model`, `imei_or_serial`, `passcode_encrypted`, `reported_issue`, `issue_category`, `intake_condition` [JSON], `estimate_amount`, `status`, `outcome`, `received_at`, `ready_at`, `delivered_at`, `warranty_days`, `warranty_until`, `parent_ticket_id`, `is_deleted`).
4. `ticket_items`: Line items (`ticket_id`, `inventory_item_id`, `type` [`labor`|`part`], `description`, `price_charged`, `cost_price`, `supplier_name`, `is_deleted`).
5. `payments`: Payment records (`ticket_id`, `amount` [signed integer; negative for refunds], `mode` [`cash`|`upi`|`card`], `kind` [`advance`|`partial`|`final`|`refund`], `paid_at`, `is_deleted`).
6. `status_history`: History log (`ticket_id`, `from_status`, `to_status`, `changed_at`, `note`).
7. `cash_closings`: Daily cash records (`date` [unique], `opening_cash`, `expected_cash`, `counted_cash`, `variance`, `is_closed`, `closed_at`, `reopened_at`).
8. `audit_log`: Immutable audit entries (`entity`, `entity_id`, `ticket_id`, `action`, `changed_fields` [JSON], `reason`, `timestamp`).
9. `inventory_items`: Stock master (`spare_type`, `model`, `quantity`, `cost_price`, `selling_price`, `supplier_name`, `is_deleted`).

### SQLite Database Triggers:
- `trg_no_delete_tickets`: Aborts `DELETE` on `tickets`.
- `trg_no_delete_payments`: Aborts `DELETE` on `payments`.
- `trg_no_delete_ticket_items`: Aborts `DELETE` on `ticket_items`.
- `trg_no_delete_status_history`: Aborts `DELETE` on `status_history`.
- `trg_no_delete_audit_log`: Aborts `DELETE` on `audit_log`.
- `trg_no_update_audit_log`: Aborts `UPDATE` on `audit_log`.

---

## 7. Configuration & Environment Variables

All settings are managed via `.env` or system environment variables (`app/config.py`).

| Variable Name | Required | Default in Development | Description |
|---|---|---|---|
| `APP_ENV` | Optional | `development` | Set to `production` in live environments. |
| `SECRET_KEY` | **Required** | Dev fallback (rejected in prod) | Key for signing session cookies. Must be >= 16 chars in production. |
| `PASSCODE_ENCRYPTION_KEY`| **Required** | Predefined dev Fernet key | Base64-encoded 32-byte key for symmetric encryption of device PINs. |
| `DATABASE_URL` | Optional | `sqlite:///data/shop.db` | SQLite database URI. |
| `BACKUP_DIR` | Optional | `backups` | Target folder for online SQLite database backups. |
| `COOKIE_SECURE` | Optional | `false` | Set to `true` when serving behind HTTPS to enforce secure cookies. |

*Note: Use `python scripts/gen_key.py` to generate secure keys for `SECRET_KEY` and `PASSCODE_ENCRYPTION_KEY`.*

---

## 8. How to Install, Run, Build & Test

### Prerequisites:
- Python 3.12+
- `uv` package manager

### Setup & Run:
```bash
# 1. Install dependencies
uv sync

# 2. Run database migrations
uv run alembic upgrade head

# 3. (Optional) Seed realistic 90-day demo database
uv run python -m scripts.seed --reset

# 4. Start local development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Open [http://localhost:8000](http://localhost:8000).

### Running Tests & Linting:
```bash
# Run complete test suite (60 tests)
uv run pytest

# Run with test coverage report on service layer
uv run pytest --cov=app/services --cov-report=term-missing

# Run code style and lint check
uv run ruff check .
```

### Manual Backup Trigger:
```bash
uv run python -c "from app.services.backup import create_backup; print(create_backup())"
```

---

## 9. Current Implementation Status & Known Considerations

### Status:
- All core milestones and acceptance criteria (AC1 to AC9) are implemented and verified.
- Full test suite passes (60 of 60 tests passing with zero failures).

### Architectural Quirks & Known Considerations:
1. **Suppliers & Ledger System:** Suppliers and payments are tracked in tables `suppliers` and `supplier_payments`, with foreign key links `ticket_items.supplier_id` and `inventory_items.supplier_id`. Migrations are tracked in `b2c3d4e5f6a7_add_suppliers_schema.py`. Anti-delete triggers protect both tables (`trg_no_delete_suppliers` and `trg_no_delete_supplier_payments`).
2. **Inventory Migration in Alembic:** The table `inventory_items` and `ticket_items.inventory_item_id` (along with the anti-delete trigger `trg_no_delete_inventory_items`) are fully provisioned and tracked by Alembic migration `a1b2c3d4e5f6_add_inventory_schema.py`.
3. **WeasyPrint Fallback:** Thermal receipts and invoices use browser print styles (`@media print`) and print CSS rather than server-side headless browser generation (e.g. WeasyPrint) due to Windows binary compilation complexities (ADR `A-01`).
4. **Single Shop Design:** The system is single-tenant and single-shop. Admin authentication uses a single admin password and an owner PIN stored in the `settings` table rather than a multi-user RBAC table (ADR `A-28`).
5. **Soft Delete Policy:** No rows are physically deleted from operational tables. Soft-deletion flags (`is_deleted=True`) with deletion reasons are used throughout.

---

## 10. Important Constraints & Architectural Conventions

- **Integer Currency:** All monetary values (estimates, prices charged, parts costs, payments, refunds, cash drawer counts, and metrics) are stored and manipulated as integers representing Rupees (no floating-point types).
- **Timezone Discipline:** 
  - All timestamps stored in SQLite are UTC via the `UTCDateTime` custom type decorator.
  - All day-boundary queries (e.g. daily cash closing, dashboard date filters, revenue charts) **must** be converted to `Asia/Kolkata` (IST) using `app.timeutil.business_date()` or `app.timeutil.ist_day_bounds()`.
- **Append-Only Auditing:** Destructive or sensitive actions (passcode reveals, line item deletions on delivered tickets, cash drawer reopenings, refunds) must call `record_audit(...)` with an explicit reason.
- **Delivery Gate Integrity:** A ticket cannot reach `delivered` status if `balance_due != 0` unless explicitly flagged with `confirm_pending_balance=True`.
- **FastAPI / HTMX Integration:**
  - Route handlers return full HTML pages or partial Jinja2 snippets depending on `HX-Request` headers.
  - CSRF protection is verified on all mutating HTTP methods (`POST`, `PUT`, `DELETE`, `PATCH`).
- **Coding Conventions:** Target Python 3.12 syntax, Ruff line-length 120, explicit type hints, and repository services isolated from HTTP routing concerns.
