import csv
import io
from datetime import UTC, date, datetime
from typing import Any

import openpyxl
from sqlalchemy.orm import Session

from app.formatting import normalize_phone, parse_money
from app.models.enums import Outcome, PaymentKind, PaymentMode, TicketStatus
from app.models.payment import Payment
from app.models.settings import Settings as SettingsModel
from app.models.status_history import StatusHistory
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.services.audit import record_audit
from app.services.tickets import generate_ticket_number, get_or_create_customer
from app.timeutil import IST, business_date, ist_day_to_utc_bounds, utc_now


def parse_flexible_date(raw_val: Any) -> datetime | None:
    """Parse date from string or datetime/date object to timezone-aware UTC datetime."""
    if not raw_val:
        return None
    if isinstance(raw_val, datetime):
        if raw_val.tzinfo is None:
            return raw_val.replace(tzinfo=IST).astimezone(UTC)
        return raw_val.astimezone(UTC)
    if isinstance(raw_val, date):
        dt = datetime.combine(raw_val, datetime.min.time(), tzinfo=IST)
        return dt.astimezone(UTC)

    s = str(raw_val).strip()
    if not s:
        return None

    formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%b-%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            d = datetime.strptime(s, fmt)
            return d.replace(tzinfo=IST).astimezone(UTC)
        except ValueError:
            pass
    return None


def extract_rows_from_file(file_bytes: bytes, filename: str) -> tuple[list[str], list[list[Any]]]:
    """Extract header list and rows from uploaded CSV or Excel file."""
    if filename.lower().endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        all_rows = list(sheet.iter_rows(values_only=True))
        if not all_rows:
            return [], []
        headers = [str(cell).strip() if cell is not None else f"Column_{i+1}" for i, cell in enumerate(all_rows[0])]
        data_rows = [list(row) for row in all_rows[1:] if any(row)]
        return headers, data_rows
    else:
        # CSV
        text_content = file_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text_content))
        all_rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not all_rows:
            return [], []
        headers = [h.strip() for h in all_rows[0]]
        data_rows = all_rows[1:]
        return headers, data_rows


def process_import(
    db: Session,
    headers: list[str],
    data_rows: list[list[Any]],
    mapping: dict[str, str],
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate and optionally commit imported tickets.

    mapping maps field_name -> header_name.
    Required fields: phone, customer_name, device_brand, device_model, reported_issue.
    Optional fields: received_date, delivered_date, amount, payment_mode.
    """
    current_time = now or utc_now()
    header_indices = {h: idx for idx, h in enumerate(headers)}

    def get_cell(row: list[Any], field_key: str) -> Any:
        col_name = mapping.get(field_key)
        if col_name and col_name in header_indices:
            idx = header_indices[col_name]
            return row[idx] if idx < len(row) else None
        return None

    valid_rows = []
    error_rows = []
    skipped_duplicates = 0

    setting = db.query(SettingsModel).filter_by(id=1).first()
    default_warranty = setting.default_warranty_days if setting else 30

    for row_idx, row in enumerate(data_rows, start=2):  # Row 1 is header
        try:
            phone_raw = get_cell(row, "phone")
            name_raw = get_cell(row, "customer_name")
            brand_raw = get_cell(row, "device_brand")
            model_raw = get_cell(row, "device_model")
            issue_raw = get_cell(row, "reported_issue")

            if not phone_raw or not name_raw or not brand_raw or not model_raw or not issue_raw:
                raise ValueError("Missing required fields (phone, name, brand, model, issue)")

            phone = normalize_phone(str(phone_raw))
            name = str(name_raw).strip()
            brand = str(brand_raw).strip()
            model = str(model_raw).strip()
            issue = str(issue_raw).strip()

            rec_date = parse_flexible_date(get_cell(row, "received_date")) or current_time
            del_date = parse_flexible_date(get_cell(row, "delivered_date")) or rec_date

            amt_raw = get_cell(row, "amount")
            amount = parse_money(amt_raw) if amt_raw is not None else 0

            mode_raw = str(get_cell(row, "payment_mode") or "").strip().lower()
            mode = mode_raw if mode_raw in (PaymentMode.CASH.value, PaymentMode.CARD.value, PaymentMode.UPI.value) else PaymentMode.CASH.value

            # Check duplicate (same phone + model + received date)
            # Find customer first if exists
            rec_ist_date = business_date(rec_date)
            start_bound, end_bound = ist_day_to_utc_bounds(rec_ist_date)
            existing_ticket = (
                db.query(Ticket)
                .join(Ticket.customer)
                .filter(
                    Ticket.customer.has(phone=phone),
                    Ticket.device_model == model,
                    Ticket.received_at >= start_bound,
                    Ticket.received_at <= end_bound,
                    Ticket.is_deleted.is_(False),
                )
                .first()
            )
            if existing_ticket:
                skipped_duplicates += 1
                continue

            valid_rows.append({
                "row_num": row_idx,
                "phone": phone,
                "name": name,
                "brand": brand,
                "model": model,
                "issue": issue,
                "received_at": rec_date,
                "delivered_at": del_date,
                "amount": amount,
                "mode": mode,
            })
        except Exception as e:
            error_rows.append({
                "row_num": row_idx,
                "error": str(e),
                "data": [str(c) for c in row],
            })

    if not dry_run and valid_rows:
        # Atomic commit
        for item in valid_rows:
            customer, _ = get_or_create_customer(db, item["phone"], item["name"], now=current_time)
            ticket_no = generate_ticket_number(db)

            ticket = Ticket(
                ticket_no=ticket_no,
                customer_id=customer.id,
                device_brand=item["brand"],
                device_model=item["model"],
                reported_issue=item["issue"],
                issue_category="Other",
                intake_condition={"notes": "Imported ticket"},
                status=TicketStatus.DELIVERED.value,
                outcome=Outcome.REPAIRED.value,
                received_at=item["received_at"],
                ready_at=item["delivered_at"],
                delivered_at=item["delivered_at"],
                warranty_days=default_warranty,
                is_deleted=False,
            )
            db.add(ticket)
            db.flush()

            # Status history
            db.add(StatusHistory(
                ticket_id=ticket.id,
                from_status=None,
                to_status=TicketStatus.DELIVERED.value,
                changed_at=item["delivered_at"],
                note="Imported repair",
            ))

            # One labor line
            db.add(TicketItem(
                ticket_id=ticket.id,
                type="labor",
                description="Imported repair",
                price_charged=item["amount"],
                cost_price=0,
                is_deleted=False,
            ))

            # Final payment if amount > 0
            if item["amount"] > 0:
                db.add(Payment(
                    ticket_id=ticket.id,
                    amount=item["amount"],
                    mode=item["mode"],
                    kind=PaymentKind.FINAL.value,
                    paid_at=item["delivered_at"],
                    note="Imported payment",
                    is_deleted=False,
                ))

            record_audit(
                db=db,
                entity="ticket",
                entity_id=ticket.id,
                ticket_id=ticket.id,
                action="create",
                reason="import",
                now=current_time,
            )

        db.commit()

    return {
        "total_rows": len(data_rows),
        "valid_count": len(valid_rows),
        "error_count": len(error_rows),
        "skipped_duplicates": skipped_duplicates,
        "preview": valid_rows[:20],
        "errors": error_rows,
    }
