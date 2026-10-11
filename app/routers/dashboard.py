import csv
import io
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, require_pin_unlock
from app.models.settings import Settings as SettingsModel
from app.services.reports import (
    compute_comparison_pct,
    compute_reports,
    get_previous_period_bounds,
)
from app.templating import templates
from app.timeutil import business_date

router = APIRouter(prefix="/dashboard", dependencies=[Depends(require_login), Depends(require_pin_unlock)])


def get_preset_dates(preset: str) -> tuple[date, date]:
    today = business_date()
    if preset == "last_month":
        # First day of last month to last day of last month
        first_of_this_month = today.replace(day=1)
        last_of_last_month = first_of_this_month - timedelta(days=1)
        first_of_last_month = last_of_last_month.replace(day=1)
        return first_of_last_month, last_of_last_month
    else:
        # Default: this month (first of this month to today)
        first_of_this_month = today.replace(day=1)
        return first_of_this_month, today


@router.get("", response_class=HTMLResponse)
def dashboard_view(
    request: Request,
    preset: str = Query("this_month"),
    from_date_str: str | None = Query(None, alias="from"),
    to_date_str: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    if from_date_str and to_date_str:
        try:
            from_date = date.fromisoformat(from_date_str)
            to_date = date.fromisoformat(to_date_str)
            active_preset = "custom"
        except ValueError:
            from_date, to_date = get_preset_dates(preset)
            active_preset = preset
    else:
        from_date, to_date = get_preset_dates(preset)
        active_preset = preset

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Current period metrics
    rep = compute_reports(db, from_date, to_date)

    # Previous period comparison (A-21)
    prev_from, prev_to = get_previous_period_bounds(from_date, to_date)
    prev_rep = compute_reports(db, prev_from, prev_to)

    comparisons = {
        "gross_revenue": compute_comparison_pct(rep["gross_revenue"], prev_rep["gross_revenue"]),
        "billed_value": compute_comparison_pct(rep["billed_value"], prev_rep["billed_value"]),
        "parts_cost": compute_comparison_pct(rep["parts_cost"], prev_rep["parts_cost"]),
        "gross_margin_rupees": compute_comparison_pct(rep["gross_margin_rupees"], prev_rep["gross_margin_rupees"]),
        "devices_serviced": compute_comparison_pct(rep["devices_serviced"], prev_rep["devices_serviced"]),
        "avg_turnaround_hours": compute_comparison_pct(rep["avg_turnaround_hours"], prev_rep["avg_turnaround_hours"]),
        "fix_success_rate": compute_comparison_pct(rep["fix_success_rate"], prev_rep["fix_success_rate"]),
    }

    # Chart datasets JSON serialization
    chart_data = {
        "daily_labels": [d["date"] for d in rep["daily_trend"]],
        "daily_values": [d["amount"] for d in rep["daily_trend"]],
        "modes_labels": ["Cash", "Card", "UPI"],
        "modes_values": [
            rep["mode_totals"]["cash"],
            rep["mode_totals"]["card"],
            rep["mode_totals"]["upi"],
        ],
        "brands_labels": [b[0] for b in rep["top_brands"]],
        "brands_values": [b[1] for b in rep["top_brands"]],
        "models_labels": [m[0] for m in rep["top_models"]],
        "models_values": [m[1] for m in rep["top_models"]],
        "issues_labels": [i[0] for i in rep["top_issues"]],
        "issues_values": [i[1] for i in rep["top_issues"]],
        "variance_labels": [v["date"] for v in rep["variance_history"]],
        "variance_values": [v["variance"] for v in rep["variance_history"]],
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "from_date": from_date,
            "to_date": to_date,
            "active_preset": active_preset,
            "rep": rep,
            "prev_rep": prev_rep,
            "comparisons": comparisons,
            "chart_json": json.dumps(chart_data),
        },
    )


@router.get("/export/{table_name}.csv")
def export_table_csv(
    table_name: str,
    from_date_str: str = Query(..., alias="from"),
    to_date_str: str = Query(..., alias="to"),
    db: Session = Depends(get_db),
):
    try:
        from_date = date.fromisoformat(from_date_str)
        to_date = date.fromisoformat(to_date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date range")

    rep = compute_reports(db, from_date, to_date)
    output = io.StringIO()
    # UTF-8 with BOM for Excel compatibility
    output.write("\ufeff")
    writer = csv.writer(output)

    if table_name == "parts":
        writer.writerow(["Description", "Units Bought", "Total Cost"])
        for p in rep["most_bought_parts"]:
            writer.writerow([p["description"], p["count"], p["total_cost"]])

    elif table_name == "variance":
        writer.writerow(["Date", "Opening Cash", "Expected Cash", "Counted Cash", "Variance", "Note"])
        for v in rep["variance_history"]:
            writer.writerow([v["date"], v["opening"], v["expected"], v["counted"], v["variance"], v["note"] or ""])

    elif table_name == "daily_revenue":
        writer.writerow(["Date", "Net Revenue"])
        for d in rep["daily_trend"]:
            writer.writerow([d["date"], d["amount"]])

    elif table_name == "brands":
        writer.writerow(["Brand", "Repairs Received"])
        for b, count in rep["top_brands"]:
            writer.writerow([b, count])

    elif table_name == "models":
        writer.writerow(["Model", "Repairs Received"])
        for m, count in rep["top_models"]:
            writer.writerow([m, count])

    elif table_name == "issues":
        writer.writerow(["Issue Category", "Repairs Received"])
        for issue, count in rep["top_issues"]:
            writer.writerow([issue, count])

    else:
        raise HTTPException(status_code=404, detail="Unknown export table")

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={table_name}_{from_date}_{to_date}.csv"},
    )
