# MASTER_SPEC.md: Mobile Repair Shop Management System

> **Audience:** AntiGravity (AI coding agent). **Status:** single source of truth for design, build, test and delivery.
> **Source:** client file `REQUIREMENTS.md`. Nothing in that file is dropped or contradicted here.
> **Tags:** **[R]** = explicit client requirement. **[A-nn]** = assumption or decision made in this spec (all collected in section 20 and must be copied to `DECISIONS.md`).
> **Precedence:** a **[R]** always beats an **[A]**. If this spec is silent or ambiguous, choose the simplest option, record it in `DECISIONS.md`, and continue. Do not add features that are not listed here.

---

## 0. How AntiGravity must work (mandatory process)

1. Build **phase by phase, milestone by milestone** (section 18). Do not start a milestone until the previous one passes its exit checks.
2. After each milestone: run `uv run pytest`, run the app, and exercise every new screen and button in a real browser (or an equivalent HTTP-level smoke script). Fix every error before moving on.
3. **No static mockups, hard-coded fake data, dead buttons, `TODO` stubs, or half-wired forms.** Every visible control must work end to end and persist to the database. If a control cannot be built in the current phase, do not render it.
4. Business rules live in `app/services/` as plain, unit-testable Python. Routers stay thin. Rules are enforced on the **server**; the UI only hides invalid actions as a convenience.
5. Write tests alongside the code, not at the end. A milestone without its tests is not done.
6. Commit after each milestone with a clear message (if git is available). Never commit `.env`, `*.db`, `backups/`.
7. Before delivery, run the full verification protocol (section 19) and the Definition of Done (section 21).

---

## 1. Problem and scope

### 1.1 Business context [R]
A small mobile phone **repair** shop. Repairs only, no retail sales. One staff user (the owner), one Windows desktop PC, desktop browser (Chrome/Edge), no printer, reliable internet. About 10 repairs/day (about 3,600/year). Spare parts are bought per job, so **there is no stock to manage**. Currency ₹ with Indian grouping (₹1,25,000). Payments: Cash, Card, UPI. No GST/tax invoicing, plain receipts only. Timezone Asia/Kolkata.

### 1.2 Goals [R]
1. Every repair recorded from intake to delivery with full history.
2. Every payment linked to a ticket; daily cash reconciled.
3. No paper: digital receipt and ticket identification (QR).
4. Owner sees monthly sales, margins and repair trends on demand.

### 1.3 Users
One login (shop owner/staff). A separate **owner PIN** guards destructive actions and analytics. No roles, no multi-user.

### 1.4 Out of scope [R]
GST/tax invoicing, parts stock management, multi-user roles, official WhatsApp Business API, SMS gateway, payment gateway integration, expense/payroll tracking, printing hardware support. Do not build any of these. Do not auto-change statuses or auto-escalate unclaimed devices.

### 1.5 Expected outcomes
A working, tested app where a ticket is created in under 2 minutes, searched in under 1 second, paid in splits, reconciled daily, backed up nightly, and analysed from the dashboard, with numbers verified by tests.

---

## 2. Technology and architecture

### 2.1 Stack [R]
- Python 3.12 managed by **uv** (`uv init`, `uv add`, `uv run`; never `pip` directly).
- FastAPI, SQLAlchemy 2.x (typed `Mapped[]` style), Alembic, SQLite (WAL, foreign keys ON).
- Jinja2 + HTMX + Tailwind CSS (CDN) + Chart.js. No JS framework, no build step.
- Auth: single user, argon2 password hash, session cookie.
- pytest. Dockerfile. Run locally with `uv run uvicorn app.main:app --reload`.

### 2.2 Dependencies (add with `uv add`)
Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `jinja2`, `python-multipart`, `itsdangerous`, `argon2-cffi`, `cryptography` (Fernet), `qrcode`, `openpyxl` (xlsx import), `tzdata` (**required for `Asia/Kolkata` on Windows**), `apscheduler`, `pydantic-settings`.
Dev: `pytest`, `httpx`, `pytest-cov`, `ruff`.
Pin CDN assets to exact versions: htmx 2.0.x, Tailwind Play CDN, Chart.js 4.x.

### 2.3 PDF decision [A-01]
WeasyPrint needs native GTK libraries that are painful on Windows. The client allows "browser print-to-PDF with print CSS" as the fallback, so use it: the receipt page has a dedicated `@media print` stylesheet; the **Download PDF** button opens the browser print dialog (`window.print()`) where the user picks "Save as PDF". Label the button "Download PDF" with helper text "Choose 'Save as PDF' in the print window". QR is rendered as **inline SVG** (`qrcode.image.svg`), so Pillow is not needed.

### 2.4 Project structure
```
repair-shop/
├── pyproject.toml, uv.lock, README.md, DECISIONS.md, MASTER_SPEC.md
├── Dockerfile, .dockerignore, .env.example, .gitignore, alembic.ini
├── alembic/ (env.py with render_as_batch=True, versions/)
├── app/
│   ├── main.py            # app factory, middleware, lifespan (scheduler, startup backup check)
│   ├── config.py          # pydantic-settings: env vars
│   ├── db.py              # engine, SessionLocal, PRAGMA listener, get_db dependency
│   ├── security.py        # password/PIN hashing, session, CSRF, PIN-unlock, rate limit, Fernet
│   ├── deps.py            # require_login, require_pin_unlock, csrf dependency
│   ├── timeutil.py        # IST helpers, UTC<->IST, business_date(), day/range -> UTC bounds
│   ├── formatting.py      # format_inr, format_date, format_time, Jinja filters
│   ├── models/            # one module per table + enums.py
│   ├── services/          # tickets.py, status.py, items.py, payments.py, cash_close.py,
│   │                      # customers.py, search.py, receipts.py, warranty.py, reports.py,
│   │                      # audit.py, backup.py, settings_service.py, importer.py
│   ├── routers/           # auth, queue, tickets, items, payments, search, customers,
│   │                      # cash, dashboard, settings, importer, audit, health
│   ├── templates/         # base.html, partials/, one folder per area
│   └── static/            # app.css (print + small custom), app.js (tiny helpers only)
├── scripts/seed.py, scripts/gen_key.py
├── tests/                 # conftest.py + test_*.py
├── data/                  # shop.db (gitignored)
└── backups/               # gitignored
```
Layering: `router -> service -> models`. Services take a `Session` and an optional `now: datetime` (for deterministic tests and seeding). Services raise typed domain errors (`InvalidTransition`, `ValidationFailed`, `PinRequired`, `DayClosed`, `NeedsConfirmation`) which routers map to HTTP 409/422/403.

### 2.5 Database engine configuration [R]
On every SQLite connection (SQLAlchemy `connect` event): `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA synchronous=NORMAL;`. Handle the pysqlite transaction quirk so write transactions begin with `BEGIN IMMEDIATE` (event hooks on `begin`) to avoid deadlocks. **Run exactly one uvicorn worker** (SQLite writer plus in-process scheduler); document this in README and Dockerfile.

### 2.6 Time handling [A-02]
Store all timestamps as **UTC, timezone-aware** (custom `TypeDecorator`). Display and all "day" logic use `ZoneInfo("Asia/Kolkata")`. `business_date(dt)` returns the IST calendar date. Range queries convert IST day boundaries to UTC bounds. Never use `datetime.utcnow()` or naive datetimes.

### 2.7 Money [R]
Integer **rupees** everywhere (Python `int`, SQLite `INTEGER`). No floats, no `Decimal`. Percentages computed from integers and rounded half-up to 1 decimal at display time only. `format_inr(n)`: Indian grouping, `₹` prefix, negatives as `-₹5,000`. Examples: `999 -> ₹999`, `125000 -> ₹1,25,000`, `1234567 -> ₹12,34,567`, `0 -> ₹0`.

### 2.8 Display formats [R]
Dates `DD-MMM-YYYY` (e.g. `09-Oct-2026`), times 12-hour (`03:45 PM`). Jinja filters: `inr`, `date_ist`, `time_ist`, `datetime_ist`, `days_ago`. Raw inputs for money are plain integers (strip commas/spaces/₹; reject decimals with "Enter whole rupees").

### 2.9 Configuration (env vars, `.env`, never committed) [R]
| Var | Purpose | Notes |
|---|---|---|
| `APP_ENV` | `development` or `production` | production = fail fast on missing secrets |
| `SECRET_KEY` | session signing | dev: auto-generated into `.env` if missing |
| `PASSCODE_ENCRYPTION_KEY` | Fernet key for device passcodes | dev: auto-generated; `scripts/gen_key.py` prints one |
| `DATABASE_URL` | default `sqlite:///data/shop.db` | |
| `BACKUP_DIR` | default `backups` | |
| `COOKIE_SECURE` | `true` when served over HTTPS | |

---

## 3. Data model

All tables have `id` (integer PK), `created_at`, `updated_at` (auto-maintained). Enums stored as strings with `CHECK` constraints (non-native enums). FKs are `ON DELETE RESTRICT`. **No hard-delete code paths exist** for customers, tickets, items, payments, history or audit rows [R: soft delete].

Columns/tables beyond the client's list are marked **[A]** and are minimal supports for stated requirements.

### 3.1 customers
| Column | Type | Rules |
|---|---|---|
| name | TEXT NOT NULL | 1-100 chars, trimmed |
| phone | TEXT NOT NULL **UNIQUE**, indexed | exactly 10 digits [R]; normalize by stripping spaces, `+91`, leading `0` |
| notes | TEXT NULL | max 1000 |

### 3.2 tickets
| Column | Type | Rules |
|---|---|---|
| ticket_no | TEXT UNIQUE NOT NULL | `{prefix}-{seq}`, e.g. `R-1042`; sequential, never reused (see 4.2) |
| customer_id | FK customers NOT NULL | |
| device_brand, device_model | TEXT NOT NULL | 1-60 chars |
| imei_or_serial | TEXT NULL, indexed | 5-30 alphanumerics |
| color | TEXT NULL | max 30 |
| passcode_encrypted | TEXT NULL | Fernet token; never logged, never in audit values |
| reported_issue | TEXT NOT NULL | 3-1000 chars |
| issue_category | TEXT NOT NULL default `Other` **[A-03]** | `Screen, Battery, Charging port, Water damage, Software, Speaker/Mic, Camera, Motherboard, Other` |
| intake_condition | JSON NOT NULL | schema in 3.2.1 |
| estimate_amount | INTEGER NULL | >= 0 |
| status | TEXT NOT NULL | 8 values, section 5 |
| outcome | TEXT NULL **[A-04]** | `repaired | declined | unrepairable`; set at delivery |
| technician_note | TEXT NULL | max 2000 |
| received_at | DATETIME NOT NULL | set at creation |
| ready_at | DATETIME NULL | set on entering `ready_for_pickup` |
| delivered_at | DATETIME NULL | set on `delivered` |
| warranty_days | INTEGER NOT NULL default from settings | 0-365 |
| warranty_until | DATE NULL (IST date) | set on delivery (Phase 2 logic) |
| parent_ticket_id | FK tickets NULL | warranty return link |
| is_deleted | BOOL default false | soft delete |
| deleted_reason, deleted_at | NULL **[A]** | required when deleted |

Indexes: `ticket_no` (unique), `status`, `customer_id`, `received_at`, `delivered_at`, `imei_or_serial`, `parent_ticket_id`, `is_deleted`.

#### 3.2.1 intake_condition JSON [R]
```json
{
  "screen_cracked": false,
  "powers_on": true,
  "water_damage_indicator": false,
  "back_cover_damaged": false,
  "sim_left": false,
  "memory_card_left": false,
  "charger_accessories_received": false,
  "accessories_note": "",
  "notes": ""
}
```
Booleans are checklist items (SIM tray/SIM left, memory card left, charger/accessories received are all separate items). `accessories_note` captures the "accessories received" detail from the intake field list [A-05]. `notes` is the free-text note [R].

### 3.3 ticket_items
`ticket_id` FK, `type` (`labor|part`), `description` (1-120), `price_charged` INT >= 0, `cost_price` INT >= 0, `supplier_name` NULL (parts only), `is_deleted` **[A]** (soft delete, since all deletes must be soft).
DB `CHECK`: `type='part' OR (cost_price=0 AND supplier_name IS NULL)`.

### 3.4 payments
`ticket_id` FK **NOT NULL** (no orphans possible [R]), `amount` INT, `mode` (`cash|card|upi`), `kind` (`advance|final|refund`), `paid_at` DATETIME (server-set at creation, not user-editable) [A-06], `note` TEXT NULL, `is_deleted`, `deleted_reason`, `deleted_at`.
DB `CHECK`: `amount <> 0` and `(kind='refund' AND amount<0) OR (kind<>'refund' AND amount>0)`. Refunds are entered in the UI as a positive number and stored negative; **refund requires a reason stored in `note`** [R] (min 3 chars).
Indexes: `ticket_id`, `paid_at`, `(mode, paid_at)`.

### 3.5 status_history
`ticket_id`, `from_status` (NULL for the initial `received` row), `to_status`, `changed_at`, `note` NULL. One row is written for ticket creation and for every transition [R].

### 3.6 audit_log
`entity` (`ticket|payment|item|customer` [R], plus `cash_closing|settings` [A-07]), `entity_id`, `ticket_id` NULL **[A]** (denormalized for fast per-ticket audit trail), `action` (`create|update|delete`), `changed_fields` JSON (`{"field":{"old":..,"new":..}}`; passcode fields log only `{"passcode":{"changed":true}}`), `reason` TEXT NULL **[A]** (required for deletes, reopen, deliver-with-balance, overpay), `timestamp`. Append-only; no UI or code path edits/deletes rows.

### 3.7 cash_closings
`date` (IST date, **UNIQUE**), `opening_cash`, `expected_cash` (snapshot at close), `counted_cash`, `variance` (= counted - expected), `note` NULL, `is_closed` BOOL **[A-08]**, `closed_at` NULL, `reopened_at` NULL. A row exists once the day was ever closed; reopening sets `is_closed=false` and keeps the row.

### 3.8 settings (single row, id=1)
`shop_name, shop_phone, shop_address, receipt_terms_text, default_warranty_days (default 30), owner_pin_hash, ticket_no_prefix (default "R")` [R], plus **[A]** `admin_password_hash`, `next_ticket_seq` (default 1001), `msg_template_intake`, `msg_template_ready` (defaults exactly as in 6.3), `setup_completed` BOOL.

### 3.9 Integrity extras (SHOULD)
SQLite triggers (created in the Alembic migration) that `RAISE(ABORT)` on `DELETE` for `tickets`, `payments`, `ticket_items`, `status_history`, `audit_log`, and on `UPDATE`/`DELETE` of `audit_log`. A test proves a raw `DELETE` fails.

---

## 4. Business rules

### 4.1 Customers
- Phone is the identity. Intake looks up by phone; existing -> autofill name. If the staff edits the name for an existing phone, update the customer and write an audit entry.
- Customer notes editable on the customer page (audited).

### 4.2 Ticket numbers
Generated inside the creation transaction: `UPDATE settings SET next_ticket_seq = next_ticket_seq + 1 ... RETURNING` then format `f"{prefix}-{seq}"`. Unique constraint is the safety net. Changing the prefix affects only new tickets; the sequence continues. Soft-deleted tickets never free their numbers.

### 4.3 Balance and payments [R]
- `items_total = sum(price_charged)` over non-deleted items.
- `net_paid = sum(amount)` over non-deleted payments (refunds negative).
- **`balance_due = items_total - net_paid`**. UI: `>= 0` shows "Due ₹X"; `< 0` shows "Credit ₹X (paid more than billed)".
- Multiple payments per ticket (split cash+UPI, advance+final).
- **Overpayment confirmation [R, A-09]:** reference total is `items_total` if > 0, else `estimate_amount` if set, else none (no limit). A new payment (`advance` or `final`) that makes `net_paid` exceed the reference total is rejected with HTTP 409 and a UI prompt "This exceeds the balance by ₹X. Confirm?"; resubmitting with `confirm_overpay=1` succeeds and logs an audit entry with reason "overpayment confirmed". This lets an advance be taken before any line items exist.
- **Refund rules:** refund amount <= `net_paid` of that ticket; reason required; mode chosen (cash/card/upi).
- Payment edit (amount, mode, note) is allowed only while the payment's IST day is not closed; audited with old/new values. `paid_at` and `kind` are not editable.
- Payment delete: reason + owner PIN; soft delete; audited; blocked if the payment's day is closed (reopen first).

### 4.4 Items
Add/edit/remove (soft) labor and part lines. Parts capture `cost_price` and optional `supplier_name`. Every change audited. **After a ticket is delivered, item changes require the owner PIN [A-10]** (they alter historical billed value) and are audited.

### 4.5 Ticket delete [R]
Requires reason + owner PIN. Blocked while the ticket has any non-deleted payment [A-11] (delete or refund those first, each with its own reason and PIN), so reports and cash totals never disagree. Deleted tickets vanish from queue, search, reports; the detail URL still opens read-only with a "Deleted: {reason}" banner.

### 4.6 Passcode [R]
Optional, encrypted with Fernet. Never rendered in HTML by default. "Show passcode" button (HTMX POST) reveals it for that response only and writes an audit entry (`passcode_viewed`, no value). "Clear passcode" button available any time; the delivery dialog has a checkbox "Clear device passcode" (default checked).

### 4.7 Warranty (Phase 2) [R]
- On delivery of a ticket with `outcome='repaired'` and `warranty_days > 0`: `warranty_until = IST delivery date + warranty_days`. Otherwise `NULL`. Under warranty on date D if `warranty_until >= D` (inclusive).
- Search results and ticket/customer pages show a badge: "Under warranty until DD-MMM-YYYY" or "Warranty expired".
- **Create warranty return ticket**: from a delivered, repaired ticket, opens the intake form prefilled (customer, device, IMEI, color) with `parent_ticket_id` set; reported issue empty; saves as a new `received` ticket. Parent and children link to each other on detail pages. Button visible only for delivered tickets (any, even if warranty expired, but with an "expired" warning) [A-12].

---

## 5. Ticket lifecycle [R]

Statuses: `received`, `awaiting_approval`, `in_progress`, `awaiting_parts`, `ready_for_pickup`, `delivered`, `declined`, `unrepairable`.

Transition map (single constant in `services/status.py`, used by UI and API):
```
received          -> awaiting_approval, in_progress, declined, unrepairable
awaiting_approval -> in_progress, declined
in_progress       -> awaiting_parts, ready_for_pickup, unrepairable
awaiting_parts    -> in_progress
ready_for_pickup  -> delivered, in_progress   (rework)
declined          -> delivered                (device handed back)
unrepairable      -> delivered                (device handed back)
delivered         -> (final)
```
Rules:
- Each transition writes a `status_history` row (optional note) in the same DB transaction as the ticket update.
- Entering `ready_for_pickup`: `ready_at = now` (overwritten if re-entered after rework) [A-13].
- Entering `delivered`: `delivered_at = now`; `outcome` = `repaired` if coming from `ready_for_pickup`, `declined` if from `declined`, `unrepairable` if from `unrepairable` [A-04]; `warranty_until` per 4.7.
- **Delivery gate [R]:** if `balance_due != 0`, the API returns 409 unless `confirm_pending_balance=1` is sent; when confirmed, write an audit entry (`action=update`, `changed_fields={"delivered_with_balance":{"new": balance}}`, reason "delivered with pending balance"). Negative balance (credit) is handled the same way, with the dialog text suggesting a refund.
- A diagnostic fee for declined tickets is simply a labor line [R: "optional"].
- Invalid transitions: UI shows only valid buttons; the endpoint returns **409** with a clear message if called anyway [R, AC3].
- A delivered ticket never changes status. Warranty = new linked ticket.
- No automatic changes of any kind.

---

## 6. Features

### 6.1 Auth and first run (Phase 1) [R]
- `/setup` is reachable only when `setup_completed=false`: collects shop name, admin password (min 8 chars), owner PIN (4-6 digits). Afterwards `/setup` returns 404.
- `/login`, `/logout`. Session cookie: signed, `HttpOnly`, `SameSite=Lax`, `Secure` when `COOKIE_SECURE`, **12-hour lifetime** (absolute, `max_age=43200`).
- All routes except `/login`, `/setup`, `/healthz`, static files require login; HTML requests redirect to `/login?next=`, HTMX requests receive `HX-Redirect`.
- Rate limiting [R, section 8]: 5 failed password attempts per IP in 5 minutes -> 5-minute lockout with a friendly message; same for PIN (5 wrong PINs -> 5-minute lock). In-memory is acceptable.

### 6.2 Intake / new ticket (Phase 1) [R]
Route `/tickets/new`. One page, one form, tab order top to bottom, Enter submits (except inside textareas), autofocus on phone. Target: under 2 minutes.

Field order:
1. Phone (10 digits). On 10 digits, HTMX lookup (debounce 250 ms): if found, fill name and show a panel "Past tickets" (ticket no, device, date, status, link, max 5) and a warranty badge for any device still under warranty; if not found, show "New customer".
2. Name.
3. Brand and model: text inputs with `<datalist>` autocomplete from previously used values (model list filtered by brand) via `/autocomplete/brands` and `/autocomplete/models?brand=` [R].
4. IMEI/serial (optional), color (optional).
5. Reported issue (textarea) and issue category dropdown (default Other) [A-03].
6. Intake condition checklist (7 checkboxes) + accessories note + notes.
7. Device passcode (optional, masked input).
8. Estimate (optional).
9. Advance payment (optional): amount + mode (cash/card/upi, default cash) + note (e.g. UPI ref). Creates a `kind=advance` payment dated now.
10. Save button "Create ticket & show receipt".

On save (single transaction): upsert customer, create ticket (status `received`, `warranty_days = settings default`), first `status_history` row, optional advance payment, audit entries. Redirect (303) to the receipt page. Blocked if today's cash is closed and an advance is entered (message with reopen link).

States: inline field errors under each field (server-rendered, values preserved); submit button disabled with spinner while posting; success toast "Ticket R-1042 created".

### 6.3 Digital receipt (Phase 1) [R]
Route `/tickets/{id}/receipt`. Clean, mobile-friendly, single column, max width about 480 px on phones and centered on desktop.
Contents: shop name/phone/address, ticket no, received date/time, customer name and phone, device (brand, model, color, IMEI), reported issue, condition at intake (checklist as ticks + notes), advance paid, terms text, **QR code containing exactly the ticket number** (inline SVG). Additionally, a payments summary and, once line items exist, items with total and balance [A-14] so the receipt remains useful at pickup. The passcode is **never** printed.
Buttons (hidden in print): **Send via WhatsApp**, **Download PDF** (A-01), Back to ticket.

**WhatsApp [R]:** `<a target="_blank" rel="noopener" href="https://wa.me/91{phone}?text={urlencoded message}">`. No API, always manual. Default templates (editable in settings, Phase 2; stored in `settings` from Phase 1):
- Intake: `Hi {name}, we received your {device}. Ticket {ticket_no}. Issue: {issue}. Advance paid: ₹{advance}. Thank you, {shop_name}.`
- Ready: `Hi {name}, your {device} is ready for pickup. Ticket {ticket_no}. Amount due: ₹{due}. {shop_name}`

Placeholders: `{name} {device} {ticket_no} {issue} {advance} {due} {shop_name}`. `{device}` = "Brand Model". `{advance}`/`{due}` are Indian-grouped numbers **without** the ₹ (the template contains it). `{advance}` = net paid, `{due}` = `max(balance_due, 0)`. Rendering uses safe substitution (unknown placeholders left as-is, never crash). The Ready WhatsApp button appears on the ticket detail when status is `ready_for_pickup` and on the Ready list.

Default `receipt_terms_text` (editable) [A-15]: "1. Device is accepted at the owner's risk; please back up your data. 2. Estimates may change after diagnosis and your approval will be sought. 3. Repaired devices carry the warranty stated on this receipt for the repaired part/fault only; physical or water damage voids it. 4. Please present this receipt or ticket number at pickup."

### 6.4 Ticket queue, home screen (Phase 1) [R]
Route `/`. **Grouped table** (decision: table, not board) [A-16]. Groups in order: Received, Awaiting approval, In progress, Awaiting parts, Ready for pickup, Declined (to hand back), Unrepairable (to hand back). Each group header shows a count and is collapsible.
Columns: Ticket no (link), Customer (name, phone), Device, **Age** (whole days since received), **In status** (whole days since entering the current status), Balance due (`inr`, credit shown in green as "Credit"). Rows with **In status > 7 days** get an amber background and a "7d+" badge [R].
Filters: status chips (multi-select, URL query `?status=`); default shows the 7 active statuses. A "Delivered (last 30 days)" chip adds delivered tickets. Deleted tickets never appear.
**Ready for pickup list** (`/ready`): only `ready_for_pickup`, sorted by days waiting descending (oldest first); columns ticket, customer, phone, device, days waiting, amount due, WhatsApp-reminder link (manual send). Informational only, no automation [R].
States: empty ("No tickets in this status"), loading skeleton on HTMX filter swaps, error banner on failure. On phones the table collapses to stacked cards.

### 6.5 Ticket detail (Phase 1) [R]
Route `/tickets/{id}`. Sections (two columns >= 1024 px, stacked on phones):
- **Header:** ticket no, status badge, warranty badge (Phase 2), customer link, deleted/parent/child banners.
- **Details card:** device, IMEI, color, issue, category, intake checklist, estimate, technician note, dates (received/ready/delivered), passcode block (4.6). An "Edit details" form edits issue, category, estimate, technician note, device fields and checklist (all audited).
- **Status panel:** only valid transition buttons (from map in section 5), each with optional note; delivery opens a dialog (balance summary, pending-balance confirmation, clear-passcode checkbox).
- **History timeline:** from -> to, timestamp, note.
- **Line items editor** (HTMX inline add/edit/remove for labor and part rows; part rows show cost and supplier fields; running totals).
- **Payments:** list (time, mode, kind, amount, note; deleted rows struck through with reason), "Add payment" form (amount, mode, kind advance/final/refund, note), balance card (items total, net paid, balance).
- **Audit trail** (collapsible): entries for this ticket, its items and payments.
- **Actions:** Receipt, WhatsApp (intake/ready), Create warranty return (Phase 2), Delete ticket (reason + PIN).
All mutations are HTMX partial swaps with a toast; errors render inline in the section.

### 6.6 Search (Phase 1) [R]
Search box in the global header, visible on every page. `GET /search?q=` returns an HTML dropdown fragment. HTMX trigger: `input changed delay:250ms`. Matches (case-insensitive substring, LIKE with `%`/`_` escaped) on: ticket no (so `1042` finds `R-1042`), customer name, phone, IMEI/serial, device model (and brand). Max 20 results, newest first; each row: ticket no, customer, phone, device, status, and (Phase 2) a warranty badge. Enter opens the top result; exact ticket-number match jumps straight to the ticket (also makes QR-scanner keyboard input work). Escape closes; arrow keys move selection. Min 2 characters. Empty state "No matches". **Under 1 second** on 20,000 tickets [R] (tested, section 17).

### 6.7 Daily cash close (Phase 1) [R]
Route `/cash?date=YYYY-MM-DD` (default today IST; future dates rejected).
- Lists all non-deleted payments of that IST day grouped by mode (Cash, Card, UPI): time, ticket link, kind, amount; totals per mode (net of refunds). Card and UPI totals are for reference only.
- **Opening cash** input, defaulting to the `counted_cash` of the most recent closing before this date (0 if none), editable.
- **Expected cash = opening + sum(cash payments incl. negative refunds)** for the day. Recomputes via HTMX when opening changes.
- **Counted cash** input (integer >= 0). **Variance = counted - expected**, shown live (green 0, red negative, amber positive). Optional note.
- **Close day** (confirm dialog): writes/updates the `cash_closings` row (`is_closed=true`, snapshot expected, variance, closed_at). From then, all payment creates/edits/deletes dated to that day are rejected (`DayClosed`, 409) with message "Day closed. Reopen with owner PIN to change." [R]
- **Reopen day:** owner PIN required; sets `is_closed=false`, `reopened_at`, audit entry. Re-closing recomputes expected.
- Recent closings table (last 10: date, opening, expected, counted, variance).
- Edge: today closed, then a customer pays -> staff must reopen (documented in UI banner).

### 6.8 Audit and safety (Phase 1) [R]
Every create/update/delete of customers, tickets, items, payments (and cash closings/settings) writes `audit_log`. Deleting a payment or ticket needs reason + PIN (modal with two fields; wrong PIN -> inline error, counts toward rate limit). Read-only **Audit log page** `/audit` (filter by entity, ticket no, date; shows reason and old/new values) so that AC7 is verifiable in the UI [A-17].

### 6.9 Backups (Phase 1) [R]
- Online backup via `sqlite3.Connection.backup()` to `backups/shop-YYYYMMDD-HHMMSS.db`, then prune to the **latest 30**.
- APScheduler job nightly at **02:00 IST**. Because the shop PC may be off at 02:00, also run a **catch-up backup at startup** if the newest backup is older than 24 hours [A-18].
- Settings page: **Download backup now** (creates a fresh backup and streams it), list of existing backups with size/time.
- README documents restore (stop app, copy chosen file to `data/shop.db`, delete `shop.db-wal` and `shop.db-shm`, start app) and cloud sync (rclone cron on Linux; Task Scheduler + rclone on Windows).
- Backup failures are logged and shown as a warning banner on the Settings page.

### 6.10 Customer page (Phase 2) [R]
`/customers/{id}`: name, phone, notes (editable), all tickets (non-deleted) with status/date/amount, **total spent = net payments across the customer's non-deleted tickets**, warranty badges.

### 6.11 Settings page (Phase 2) [R]
Phase 1 ships `/settings` with Backups only (plus defaults seeded from first-run setup). Phase 2 adds forms: shop details (name, phone, address), receipt terms, message templates (with placeholder help and live preview), default warranty days, ticket prefix, change password (needs current password), change PIN (needs current PIN). All audited.

### 6.12 Excel/CSV import (Phase 2) [R, "if the shop has any"]
`/import` (owner PIN unlock required). Steps: upload `.csv`/`.xlsx` (max 5 MB) -> choose sheet -> **column mapping UI** (map file columns to: phone, customer name, brand, model, issue, received date, delivered date, amount, payment mode; phone/name/brand/model/issue required) -> preview first 20 rows with validation errors per row -> commit. Rules [A-19]: imported tickets are created as `delivered`, outcome `repaired`, with one labor item "Imported repair" (price = amount) and, if amount > 0, one `final` payment dated the delivered date (mode default cash). Dates parsed as DD-MM-YYYY, DD-MMM-YYYY or ISO. Invalid rows are skipped and listed in a downloadable error CSV; duplicates (same phone + model + received date) are skipped. Everything in one transaction per file; each created record audited with reason "import". A tiny sample CSV is included in the repo.

### 6.13 Analytics dashboard (Phase 3) [R]
Route `/dashboard`, **owner PIN required**: unlock via `/pin`, valid for 15 minutes of inactivity (sliding) [A-20]; locked requests redirect to the PIN form.
Controls: preset buttons **This month**, **Last month**, **Custom** (from/to inclusive IST dates). Every KPI shows the previous period value and % change. Previous period = the immediately preceding window of equal length [A-21]; when the previous value is 0 show "n/a" instead of a percentage.
All metrics exclude soft-deleted tickets, items and payments. Definitions (exact, [R] unless tagged):

| Metric | Definition |
|---|---|
| Gross revenue | sum of `amount` of payments (net of refunds) with `paid_at` in the period |
| Billed value | sum of non-deleted `price_charged` on tickets with `delivered_at` in the period |
| Parts cost | sum of `cost_price` on part lines of those same tickets |
| Gross margin | billed value - parts cost, in ₹ and % of billed value (0% if billed = 0). Label exactly "Gross margin" (not profit) |
| Payment mode breakdown | net total and % per cash/card/upi from the same payments as gross revenue |
| Devices serviced | count of tickets with `delivered_at` in period and `outcome='repaired'` |
| Avg turnaround | mean of (`ready_at - received_at`) over tickets whose `ready_at` is in the period [A-22]; shown as days/hours |
| Avg pickup delay | mean of (`delivered_at - ready_at`) over repaired tickets delivered in the period |
| Fix success rate | repaired tickets (delivered in period) **without** a warranty return / all repaired tickets delivered in period. A warranty return is a non-deleted child ticket whose `received_at` is on or before the parent's `warranty_until` [A-23]. Also show counts of declined and unrepairable (by the date the ticket entered that status, from `status_history`) |
| Top brands / models | top 10 by ticket count, tickets with `received_at` in period [A-24] (bar charts) |
| Top recurring issues | count by `issue_category`, received in period (bar chart) |
| Most-bought parts | part lines on tickets delivered in period, grouped by `lower(trim(description))`; columns description, count, total cost, sorted by count then cost |
| Daily revenue trend | line chart, net payments per IST day across the range, zero-filled |
| Cash variance history | `cash_closings` rows in range: date, expected, counted, variance (chart + table) |

Charts: Chart.js (line for trend, doughnut for modes, horizontal bars for brands/models/issues/parts, bar for variance). Data is embedded as JSON in the page. **Every table has a CSV export button** (`/dashboard/export/{table}.csv?from=&to=`), UTF-8 with BOM, raw integers for money, ISO-like dates `DD-MMM-YYYY`. Empty range -> empty-state cards, no JS errors.

---

## 7. Routes (server-rendered; HTMX partials where noted)

Mutating routes require CSRF. Success on full-page forms -> 303 redirect; HTMX -> partial plus `HX-Trigger` toast event. Errors: 422 (validation) and 409 (rule violation/needs confirmation) return an HTML fragment that **is swapped** (configure htmx 2 `responseHandling` so 409/422 swap into the target and are not treated as network errors); 403 PIN/auth; 404 page.

| Method & path | Purpose | Phase |
|---|---|---|
| GET/POST `/setup` | first-run | 1 |
| GET/POST `/login`, POST `/logout` | auth | 1 |
| GET/POST `/pin` | unlock PIN session (`?next=`) | 1 |
| GET `/` | queue (supports `?status=` HTMX) | 1 |
| GET `/ready` | ready-for-pickup list | 1 |
| GET `/tickets/new`, POST `/tickets` | intake | 1 |
| GET `/tickets/{id}` | detail | 1 |
| POST `/tickets/{id}/edit` | edit fields | 1 |
| POST `/tickets/{id}/status` | transition (`to_status`, `note`, `confirm_pending_balance`, `clear_passcode`) | 1 |
| POST `/tickets/{id}/delete` | reason + PIN | 1 |
| POST `/tickets/{id}/passcode/reveal`, `/clear` | passcode | 1 |
| GET `/tickets/{id}/receipt` | digital receipt | 1 |
| POST `/tickets/{id}/items`, `/items/{id}`, `/items/{id}/delete` | line items | 1 |
| POST `/tickets/{id}/payments`, `/payments/{id}`, `/payments/{id}/delete` | payments (`confirm_overpay`; delete needs reason + PIN) | 1 |
| GET `/search?q=` | live search fragment | 1 |
| GET `/customers/lookup?phone=` | intake autofill fragment | 1 |
| GET `/autocomplete/brands`, `/autocomplete/models?brand=` | datalist options | 1 |
| GET `/cash?date=`, GET `/cash/expected`, POST `/cash/{date}/close`, `/cash/{date}/reopen` | cash close | 1 |
| GET `/audit` | audit log | 1 |
| GET `/settings`, POST `/settings/backup/run`, GET `/settings/backup/download` | backups | 1 |
| GET `/healthz` | health check (no auth) | 1 |
| GET `/customers/{id}`, POST `/customers/{id}` | customer page | 2 |
| POST `/settings/shop`, `/settings/templates`, `/settings/password`, `/settings/pin` | settings | 2 |
| POST `/tickets/{id}/warranty-return` (or GET prefilled `/tickets/new?parent=`) | warranty return | 2 |
| GET/POST `/import` (+ error CSV) | import | 2 |
| GET `/dashboard`, GET `/dashboard/export/{table}.csv` | analytics | 3 |

Validation summary (server-side, with friendly messages): phone 10 digits; name 1-100; brand/model 1-60; issue 3-1000; money fields integer >= 0 (payments >= 1) and <= 10,00,000 sanity cap [A-25]; item description 1-120; delete/refund reason >= 3 chars; counted/opening cash >= 0; warranty days 0-365; PIN 4-6 digits; password >= 8.

---

## 8. UI/UX

### 8.1 Layout and navigation
- **Header (all pages):** shop name, **global search box** (center, always visible), nav links: Queue, New Ticket, Ready, Cash Close, Dashboard, Settings (with Audit log inside), Logout. Header sticks to top. On phones the nav collapses to a hamburger; the search box stays visible.
- Design: Tailwind utility styling, neutral palette with one accent colour, clear status badges (consistent colour per status), 16 px base font, large click targets, optimized for 1366x768 and up, usable at 360 px width. Tables become cards below 768 px.
- Currency right-aligned in tables. Status badges: received (gray), awaiting_approval (yellow), in_progress (blue), awaiting_parts (orange), ready_for_pickup (green), delivered (dark gray), declined (rose), unrepairable (red).

### 8.2 States every screen must handle
| State | Behaviour |
|---|---|
| Loading | `htmx-indicator` spinners/skeletons on partial swaps; buttons disabled while submitting (prevents double submit) |
| Empty | Friendly message plus the next action (e.g. "No tickets yet. Create the first one") |
| Success | Toast (auto-dismiss 4 s) with what happened |
| Validation error | Inline under the field; form values preserved |
| Rule violation (409) | Inline alert in the relevant panel, or a confirm dialog when confirmation can resolve it (overpay, pending balance) |
| Auth/PIN | Redirect to login/PIN; wrong PIN message; lockout message with time remaining |
| 404 / 500 | Branded error pages with a link home; 500 shows a generic message and logs the stack trace without sensitive data |

### 8.3 Interaction details
- Keyboard-friendly intake (section 6.2); `Enter` submits; `Esc` closes dialogs/dropdowns.
- Confirmation dialogs for: delivery, close day, reopen day, delete (PIN + reason), refund, overpayment.
- Use native `<dialog>` for modals. Minimal custom JS in `static/app.js` (toasts, dialogs, search keyboard nav, print button). No JS framework.
- Accessibility basics: labels on every input, visible focus rings, sufficient contrast, `aria-live` for toasts.

---

## 9. Security [R]

- argon2 hashes for password and PIN; PIN stored hashed in `settings.owner_pin_hash`.
- CSRF protection on every state-changing request: per-session token, validated from the `csrf_token` form field or the `X-CSRF-Token` header (htmx sends it via `hx-headers` on `<body>`). Failure -> 403.
- Session cookie: HttpOnly, SameSite=Lax, Secure when `COOKIE_SECURE`, 12-hour max age. Regenerate session on login.
- Login and PIN rate limiting (6.1). Optional: if deployed publicly, run behind HTTPS reverse proxy (Caddy example in README) with `--proxy-headers`.
- Device passcodes encrypted at rest (Fernet, key from env), revealed only by explicit click (audited), clearable, optional clear on delivery.
- Jinja autoescape on; SQLAlchemy parameter binding only; LIKE wildcards escaped; file uploads (import) validated by extension and size, parsed in memory.
- Secrets only in `.env` (gitignored, `.env.example` committed). **No sensitive data in logs**: never log request bodies, passcodes, PINs, passwords; log levels INFO for app events.
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`.
- Backups contain customer data: README warns to keep the cloud destination private (passcodes remain encrypted; the key is not in backups).

---

## 10. Reliability and performance [R]

- Page loads < 1 s in normal use; search < 1 s with 20,000 tickets; target server time < 300 ms p95 for queue, detail, search.
- Avoid N+1 queries: queue and search use aggregated subqueries/`selectinload`; balance for lists computed with a single grouped query.
- Each user action is one DB transaction; multi-step services (create ticket, deliver, close day, import) are atomic.
- Global exception handler returns the friendly 500 page; HTMX requests receive an error fragment/toast, not a blank screen.
- Startup: run `alembic upgrade head` automatically in Docker; locally via documented command; app refuses to start in production if secrets are missing.
- Nightly backup plus catch-up (6.9). `/healthz` returns `{"status":"ok"}` and checks a trivial DB query.
- Chrome and Edge current versions supported.

---

## 11. Seed data (`scripts/seed.py`) [R]

Command: `uv run python -m scripts.seed` (refuses to run on a non-empty DB unless `--reset`). Deterministic (`random.seed(42)`), dates **relative to today** so "this month" and "last month" always have data. Goes through the **service layer** (with `now=` overrides) so every invariant holds and audit/history rows exist.

Contents (about **60 tickets over 3 months**):
- 25-30 customers with realistic Indian names and valid-looking 10-digit phones (including a few repeat customers).
- Realistic devices: Samsung (Galaxy A32/M31/S21), Redmi/Xiaomi (Note 10/11/12), Realme, Vivo (Y20/V21), Oppo, OnePlus (Nord), Apple (iPhone 11/12/13), Motorola, Poco.
- Realistic issues and prices: display replacement ₹1,800-₹6,500 (part cost about 65-75% of charge), battery ₹600-₹1,800, charging port ₹400-₹900, software/flash ₹200-₹500, water damage ₹500-₹2,500, speaker/mic, camera, motherboard.
- Status mix: about 45 delivered repaired (some with split cash+UPI payments), 4 declined (2 with diagnostic fee), 3 unrepairable, and about 8 active tickets across received/awaiting_approval/in_progress/awaiting_parts/ready_for_pickup, **including two active tickets older than 7 days in status** and three ready-for-pickup tickets with different waiting times.
- 3 warranty return tickets linked to repaired parents (one failing within warranty), 2 refunds, 1 ticket delivered with pending balance (audited), 1 soft-deleted payment and 1 soft-deleted ticket (both with reasons).
- Daily cash closings for most past days with a few non-zero variances (small, e.g. -50, +20, -100); today left open.
- Customers' passcodes on a few tickets (encrypted).
- Demo credentials printed at the end and documented in README as **demo only**: password `demo12345`, PIN `1234`.

---

## 12. Setup, run and deployment

README.md must contain: prerequisites (Python 3.12, uv), `uv sync`, create `.env` (copy `.env.example`, `uv run python scripts/gen_key.py`), `uv run alembic upgrade head`, optional seed, `uv run uvicorn app.main:app --reload`, first-run setup walk-through, running tests, backup/restore, rclone sync (Linux cron and Windows Task Scheduler), starting automatically on Windows login (Task Scheduler), Docker build/run, VPS notes (HTTPS via Caddy, `COOKIE_SECURE=true`, single worker, volume mounts for `data/` and `backups/`).

**Dockerfile [R]:** `python:3.12-slim`, install uv, copy `pyproject.toml`/`uv.lock` first for layer caching, `uv sync --frozen --no-dev`, non-root user, `VOLUME` for `/app/data` and `/app/backups`, `EXPOSE 8000`, entrypoint runs `alembic upgrade head` then `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers`, `HEALTHCHECK` on `/healthz`. Include `.dockerignore`. Verify `docker build` succeeds if Docker is available; otherwise state that it was not verifiable.

---

## 13. Alembic

- Initial migration creates all tables, constraints, indexes, triggers, and inserts the single `settings` row. `render_as_batch=True` for SQLite. Migration autogenerate must show **no diff** against the models at delivery (add a test).
- Phase 2/3 columns (`warranty_*`, `parent_ticket_id`, `issue_category`, `outcome`) already exist in the first migration so no data backfill is needed; later phases only add logic and UI [A-26].

---

## 14. Testing

### 14.1 Tooling
pytest with fixtures: temp SQLite DB per test (migrated via Alembic or `create_all` plus a separate migration test), `TestClient` (httpx) with logged-in session helper, CSRF helper, frozen/injected `now`, factories for customers/tickets/items/payments.

### 14.2 Required unit/integration tests (each maps to a requirement)
**Status transitions [R, AC3]:** every allowed edge succeeds; every non-allowed pair (full 8x8 matrix) raises `InvalidTransition`/409; `status_history` row per transition; `ready_at`, `delivered_at`, `outcome` set correctly; delivered is final; rework sets `ready_at` again on re-entry; unrepairable/declined -> delivered gives matching `outcome`.
**Delivery gate:** balance 0 delivers; balance > 0 -> 409 without confirm, success with confirm plus audit row; negative balance behaves the same; passcode cleared when box checked.
**Balance [R]:** items only; items + advance; split cash+UPI; refund reduces net paid; soft-deleted items/payments excluded; credit state; the AC4 scenario (advance cash + remainder UPI -> correct balance and both payments listed).
**Payments:** overpayment needs `confirm_overpay`; advance with no items allowed against estimate; refund > net paid rejected; refund requires reason; sign/kind CHECK constraints enforced at DB level; payment without ticket impossible (FK/NOT NULL) [AC5]; payment edit/delete blocked on closed day; delete requires PIN and reason.
**Cash close [R, AC6]:** expected = opening + cash - cash refunds; card/UPI excluded from expected; variance sign; opening defaults to previous counted; close makes day read-only; reopen needs PIN and audits; IST day boundary test (a payment at 23:50 IST belongs to that IST date, at 00:10 next); re-close recalculates.
**Reports [R, AC8]:** golden dataset in 14.3 plus an **independent cross-check** on seed data: compute every metric with raw SQL/pure Python in the test and compare with `services/reports.py` output. Also: period comparison, empty period, zero-division safety, soft-deleted exclusion, CSV export content.
**Audit [R, AC7]:** every create/update/delete writes an entry; ticket/payment delete requires reason + PIN; soft-deleted rows remain; hard `DELETE` rejected by triggers; passcode value never present in audit JSON.
**Formatting:** `format_inr` table (0, 999, 1000, 99999, 100000, 125000, 1234567, -5000); date/time formats; phone normalization.
**Search:** matches by ticket no (`1042` and `R-1042`), name, phone, IMEI, model; wildcard characters escaped; **performance test**: 20,000 generated tickets, search p95 < 1 s.
**Security:** unauthenticated access redirects; CSRF missing -> 403; session expiry at 12 h; rate limit lockout; passcode ciphertext differs from plaintext and decrypts back; PIN-gated routes (`/dashboard`, import, delete, reopen) deny without PIN.
**Backups [AC9]:** backup creates a valid SQLite file that opens and passes `PRAGMA integrity_check`; pruning keeps 30; catch-up logic triggers when newest backup > 24 h old; restore procedure test (copy backup over DB, app reads data).
**Intake:** the whole flow in one test: new customer + ticket + advance -> ticket no `R-1001`, status history, payment, receipt renders QR SVG and WhatsApp URL (`https://wa.me/91<phone>?text=` encoded, placeholders replaced).
**Warranty (Phase 2):** `warranty_until` computed; badge logic inclusive on last day; warranty return links parent; zero-day warranty gives NULL.
**Import (Phase 2):** valid file, bad rows reported, duplicates skipped, atomicity.
**Migrations:** upgrade from empty DB to head succeeds; no autogenerate drift.

### 14.3 Golden dataset for report tests (hand-calculated, IST times)
Period under test: **01-Sep-2026 to 30-Sep-2026**; the previous period is empty. All tickets have `warranty_days=30`.

| Ticket | Device / category | Timeline | Items | Payments |
|---|---|---|---|---|
| T1 | Samsung Galaxy A32 / Screen | received 02-Sep 10:00, ready 04-Sep 10:00, delivered 05-Sep 12:00, repaired | labor ₹500; part "Display replacement" price ₹2,500, cost ₹1,800 | ₹1,000 cash advance 02-Sep; ₹2,000 UPI final 05-Sep |
| T2 | Redmi Note 11 / Battery | received 03-Sep 10:00, ready 03-Sep 18:00, delivered 08-Sep 18:00, repaired | labor ₹400; part "Battery replacement" price ₹1,600, cost ₹1,100 | ₹2,000 card final 08-Sep; **refund** ₹200 cash 09-Sep (note "goodwill") |
| T3 | Vivo Y20 / Software | received 04-Sep, declined, delivered 04-Sep 16:00 | labor "Diagnostic fee" ₹150 | ₹150 cash final 04-Sep |
| T4 | Samsung Galaxy A32 / Water damage | received 05-Sep, unrepairable 05-Sep, delivered 10-Sep | none | none |
| T5 | Samsung Galaxy A32 / Screen | **child of T1**, received 20-Sep, still `received` | none | none |

Cash closings: 04-Sep opening ₹4,000, counted ₹4,150; 05-Sep opening (default) ₹4,150, counted ₹4,100; 09-Sep opening (default, from 05-Sep) ₹4,100, counted ₹3,950.

Expected results (tests must assert exactly):
- Gross revenue **₹4,950** (1,000 + 150 + 2,000 + 2,000 - 200).
- Billed value **₹5,150** (3,000 + 2,000 + 150 + 0). Parts cost **₹2,900**. Gross margin **₹2,250 = 43.7%**.
- Modes: cash **₹950** (19.2%), card **₹2,000** (40.4%), UPI **₹2,000** (40.4%).
- Devices serviced **2**. Avg turnaround **28 hours** (48 h and 8 h). Avg pickup delay **73 hours** (26 h and 120 h).
- Fix success **1 of 2 = 50%** (T1 has warranty return T5 received 20-Sep <= warranty_until 05-Oct). Declined **1**, unrepairable **1**.
- Top brands: Samsung 3, Redmi 1, Vivo 1. Top model: Galaxy A32 (3). Issues: Screen 2, Battery 1, Software 1, Water damage 1.
- Most-bought parts: Display replacement (1, ₹1,800), Battery replacement (1, ₹1,100).
- Daily revenue: 02-Sep ₹1,000; 04-Sep ₹150; 05-Sep ₹2,000; 08-Sep ₹2,000; 09-Sep -₹200; all other days ₹0.
- Cash closings: 04-Sep expected ₹4,150, variance 0; 05-Sep expected ₹4,150, variance **-50**; 09-Sep expected ₹3,900 (4,100 - 200), variance **+50**.

### 14.4 Acceptance criteria (measurable; all must pass)
| # | Criterion | How verified |
|---|---|---|
| AC1 | New ticket created in under 2 minutes, receipt with QR shown | Manual timed run with keyboard only plus intake integration test |
| AC2 | Search by phone, IMEI, name, ticket no returns in < 1 s | Perf test at 20,000 tickets; manual check |
| AC3 | Invalid transitions impossible from UI and rejected by API (409) | Full matrix test plus manual UI check (no invalid buttons) |
| AC4 | Cash advance + UPI remainder shows correct balance and both payments | Test and manual run |
| AC5 | No orphan payments | DB constraint test |
| AC6 | Cash close records expected, counted, variance | Cash tests and manual run |
| AC7 | Deleted tickets/payments remain in DB and appear in audit log with reason | Audit tests and `/audit` page check |
| AC8 | Dashboard numbers match manual calculation on seed data | Golden dataset test plus seed cross-check test |
| AC9 | Backup created nightly and restorable via README | Backup tests plus a real restore dry run following the README |

---

## 15. Edge cases (must be handled explicitly)

- Phone with spaces/+91/leading 0 -> normalized; 9 or 11 digits -> error. Same phone on two intakes -> same customer.
- Double-click on submit buttons does not create duplicate tickets or payments (disable on submit; server-side ticket creation idempotency not required, but tests cover button disabling markup).
- Advance entered at intake but day closed -> clear error with reopen link; ticket not created (transaction rolled back).
- Delivering a declined ticket with an advance and no items (negative balance) -> confirmation plus refund hint.
- Ticket with items but status `declined`: allowed (diagnostic fee).
- Editing items after delivery needs PIN (4.4).
- Deleting a ticket with payments is blocked (4.5).
- Refund on a ticket whose original payment was on a closed day: allowed, dated now (today's open cash day); if today is closed, rejected until reopened.
- Reopening a day with later days already closed: allowed; later closings keep their snapshots (user sees a warning that later openings may be stale) [A-27].
- Very long text inputs truncated by validation, not by DB errors.
- Windows without tzdata -> covered by dependency; startup self-check asserts `ZoneInfo("Asia/Kolkata")` loads.
- Backup directory not writable -> clear warning, app keeps running.
- Browser back button after POST uses redirects (PRG) to avoid resubmission.
- Clock/timezone: payment at 23:59 IST vs 00:01 IST lands in the correct cash day.

---

## 16. Traceability: client requirement -> where covered

| Client section | Covered in |
|---|---|
| 1 Context, 2 Goals | 1, 2.7, 2.8 |
| 3 Tech stack | 2, 12, 13 |
| 4 Data model | 3 |
| 5 Lifecycle | 5, 14.2 |
| 6.1 Login | 6.1, 9 |
| 6.2 Intake | 6.2 |
| 6.3 Receipt/WhatsApp/PDF | 6.3, 2.3 |
| 6.4 Queue | 6.4 |
| 6.5 Ticket detail | 6.5, 4.3, 4.4 |
| 6.6 Search | 6.6 |
| 6.7 Cash close | 6.7 |
| 6.8 Audit and safety | 6.8, 3.6, 3.9 |
| 6.9 Backups | 6.9 |
| Phase 2: warranty, customer, settings, import | 4.7, 6.10, 6.11, 6.12 |
| Phase 3 analytics | 6.13 |
| 7 Non-functional | 8, 10 |
| 8 Security | 9 |
| 9 Deliverables | 11, 12, 13, 14, 21 |
| 10 Acceptance criteria | 14.4 |
| 11 Out of scope | 1.4 |

---

## 17. Performance test recipe
Generate 20,000 tickets (random customers/devices) in a temp DB via a bulk helper; run 50 searches of mixed types (`R-1042`, phone fragment, name fragment, IMEI fragment, model); assert p95 < 1000 ms (target < 150 ms). Also time `/` and `/tickets/{id}` with the seed data and assert < 1000 ms.

---

## 18. Implementation order and milestones

Each milestone ends with: tests green, app runs, every new control exercised in the browser, no console errors.

**Phase 1: MVP**
- **M0 Foundation:** `uv init`, dependencies, project skeleton, config, DB engine with PRAGMAs, models for all tables, first Alembic migration (including triggers and settings row), formatting/time helpers with tests. *Exit:* `alembic upgrade head` works; `format_inr`/time tests pass.
- **M1 Auth and shell:** setup, login/logout, session, CSRF, PIN service, rate limit, base layout, header, error pages. *Exit:* auth/CSRF/rate-limit tests pass.
- **M2 Tickets core:** customers service, ticket numbering, intake form (lookup, autocomplete, checklist, passcode encryption, advance payment), status service with full transition matrix, detail page with status panel and history, queue and Ready list. *Exit:* AC1, AC3 tests; manual intake in < 2 min.
- **M3 Money:** items editor, payments (split, refund, overpay confirmation), balance, delivery gate, audit service and `/audit` page, soft deletes with PIN+reason. *Exit:* AC4, AC5, AC7 tests.
- **M4 Receipt and search:** receipt page with QR, print CSS, WhatsApp links (templates from DB), global search with debounce and keyboard nav. *Exit:* AC2 test and perf test.
- **M5 Cash close and backups:** cash page, close/reopen, backup service and scheduler, settings page (backups). *Exit:* AC6, AC9 (backup part) tests.
- **Phase 1 gate:** full manual walk-through of 19.1; all Phase 1 tests green.

**Phase 2**
- **M6** Warranty logic, badges, warranty return flow. **M7** Customer page. **M8** Settings forms (shop, terms, templates with preview, warranty days, prefix, password, PIN). **M9** Import (mapping UI, preview, commit, error CSV). *Exit:* Phase 2 tests and manual checks.

**Phase 3**
- **M10** Reports service (pure functions) with golden-dataset tests first. **M11** Seed script (needs services complete). **M12** Dashboard UI: PIN gate, range picker, KPIs with comparison, charts, tables, CSV exports. *Exit:* AC8 tests; seed cross-check test.

**Finish**
- **M13** README, Dockerfile, `.env.example`, DECISIONS.md, performance test, final verification protocol (section 19), cleanup (ruff, remove dead code).

If time forces a trade-off, cut polish, never correctness: the order of priority is data integrity, business rules, tests, then visual refinement.

---

## 19. Verification protocol (run before declaring done)

### 19.1 Manual end-to-end script (do it in the browser on seeded data and on a fresh DB)
1. Fresh DB: `/setup` -> login -> queue empty state shows.
2. Intake: new phone, type brand/model (autocomplete after a second ticket), checklist, passcode, estimate, advance ₹1,000 cash -> receipt with QR, WhatsApp link opens `wa.me/91...` with the filled message, Download PDF opens print dialog with clean print layout.
3. Same phone again -> name autofills, past tickets visible.
4. Move ticket received -> awaiting_approval -> in_progress -> awaiting_parts -> in_progress -> ready_for_pickup; confirm only valid buttons appear at each step and history timeline updates.
5. Add labor and part lines (cost, supplier); add UPI payment for the remainder; try overpaying (confirmation appears); refund ₹100 with reason; delete a payment (PIN+reason).
6. Deliver with pending balance (confirmation) and with zero balance; clear passcode.
7. Search by ticket no, phone, name, IMEI, model while typing.
8. Cash close: counted differs from expected -> variance recorded; try adding a payment (blocked); reopen with PIN; close again.
9. Settings: download backup; verify the file opens (`sqlite3 ... "PRAGMA integrity_check"`); restore it following README.
10. Warranty return ticket; customer page totals; import a sample CSV; dashboard (PIN) with this month/last month/custom; export each table CSV; compare headline numbers to a manual SQL check.
11. Phone viewport (360 px): intake, queue, receipt, ticket detail usable; no horizontal scroll.
12. Attempt invalid actions by crafting requests (invalid transition, missing CSRF, no PIN) and confirm rejections.

### 19.2 Automated
`uv run ruff check .` clean, `uv run pytest` all green with coverage on `app/services` >= 90%, migration drift test green, Docker image builds (or noted as not verifiable).

---

## 20. Assumptions register (copy into `DECISIONS.md` verbatim, then append any new decisions)

| ID | Decision | Reason |
|---|---|---|
| A-01 | PDF via print CSS + browser "Save as PDF", not WeasyPrint | Client-permitted fallback; WeasyPrint is heavy on Windows |
| A-02 | Store UTC, compute days in IST; `tzdata` dependency | Correct day boundaries, Windows support |
| A-03 | `issue_category` column and dropdown from Phase 1 intake (default Other) | Listed in Phase 3, but needed early so analytics has data |
| A-04 | `tickets.outcome` (`repaired/declined/unrepairable`) set on delivery | Client's "status repaired" does not exist as a status; needed for metrics |
| A-05 | Accessories detail stored as `accessories_note` in intake JSON | Intake lists accessories separately from the checklist |
| A-06 | `paid_at` is server-set and not editable | Protects cash reconciliation |
| A-07 | Audit entities also include `cash_closing` and `settings` | "All edits" must be audited |
| A-08 | `cash_closings.is_closed/closed_at/reopened_at` | Needed to support close and reopen |
| A-09 | Overpay check uses items total, else estimate, else unlimited; advances allowed before items exist | Required to allow intake advances while honouring "cannot exceed balance" |
| A-10 | Item edits after delivery require owner PIN | Protects historical billed value |
| A-11 | Ticket deletion blocked while it has non-deleted payments | Keeps cash and revenue consistent |
| A-12 | Warranty-return button on any delivered ticket, with an "expired" warning when applicable | Simple and flexible |
| A-13 | `ready_at` overwritten on each entry to ready_for_pickup | Reflects final readiness |
| A-14 | Receipt also shows payments and items when present | Useful at pickup; still plain receipt |
| A-15 | Default terms text provided | Client left content to settings |
| A-16 | Queue is a grouped table, not a board | Fits 1366 px and phones |
| A-17 | Read-only audit log page | Needed to verify AC7 in the UI |
| A-18 | Catch-up backup at startup if last backup > 24 h old | PC may be off at 02:00 |
| A-19 | Import creates delivered/repaired tickets with one labor item and one final payment | Simplest consistent mapping |
| A-20 | PIN unlock for dashboard lasts 15 minutes, sliding | Usability vs safety |
| A-21 | Previous period = immediately preceding window of equal length | Unambiguous comparison |
| A-22 | Avg turnaround uses tickets with `ready_at` in the period | Defined window for the metric |
| A-23 | Warranty return = non-deleted child ticket received on or before parent's `warranty_until` | Concrete reading of "within their warranty period" |
| A-24 | Brand/model/issue stats use `received_at` in period | Measures demand |
| A-25 | Sanity cap ₹10,00,000 on money inputs | Catches typos |
| A-26 | All phase columns created in the first migration | Avoids backfill |
| A-27 | Reopening a past day shows a warning about later openings | Cash chain integrity |
| A-28 | Single-row `settings` also stores admin password hash, ticket sequence, and message templates | Avoids an extra users table for a single login |
| A-29 | Settings page ships in Phase 1 with Backups only; forms arrive in Phase 2 | Phase order in client doc |
| A-30 | Phone validated as 10 digits only (no 6-9 first-digit rule) | Follows the client wording exactly |

---

## 21. Definition of done

The work is done only when **all** are true:
1. Every **[R]** item in this spec is implemented, with no placeholder, dead button, or fake data in the UI.
2. All three phases' milestones passed their exit checks; the manual script in 19.1 was executed on both a fresh DB and the seeded DB without defects.
3. `uv run pytest` is green and includes the tests listed in 14.2, the golden dataset (14.3), and the performance test; `ruff` is clean.
4. All acceptance criteria AC1-AC9 are demonstrably met.
5. Seed script loads about 60 realistic tickets over 3 months and the dashboard renders all charts and tables from it.
6. Deliverables exist: working app, `README.md`, `Dockerfile` (+ `.dockerignore`), `.env.example`, Alembic migrations, seed script, tests, `DECISIONS.md` (section 20 plus any additions).
7. Backup create/restore was exercised by following the README.
8. No secrets, databases, or backups are committed; logs contain no sensitive data.
9. A short final report lists what was built per phase, test results, anything deliberately not verifiable (e.g. Docker unavailable), and every new assumption added to `DECISIONS.md`.
