from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.formatting import format_inr, parse_money
from app.models.cash_closing import CashClosing
from app.models.settings import Settings as SettingsModel
from app.services.cash_close import (
    close_cash_day,
    compute_day_cash_summary,
    get_default_opening_cash,
    reopen_cash_day,
)
from app.services.errors import PinRequired, ValidationFailed
from app.templating import templates
from app.timeutil import business_date

router = APIRouter(prefix="/cash", dependencies=[Depends(require_login)])


@router.get("", response_class=HTMLResponse)
def cash_page(
    request: Request,
    date_str: str | None = Query(None, alias="date"),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()
    today_ist = business_date()

    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = today_ist
    else:
        target_date = today_ist

    if target_date > today_ist:
        raise HTTPException(status_code=400, detail="Cannot access cash reconciliation for future dates")

    closing = db.query(CashClosing).filter_by(date=target_date).first()

    if closing:
        opening_cash = closing.opening_cash
        counted_cash = closing.counted_cash
        is_closed = closing.is_closed
    else:
        opening_cash = get_default_opening_cash(db, target_date)
        counted_cash = opening_cash
        is_closed = False

    summary = compute_day_cash_summary(db, target_date, opening_cash)
    expected_cash = closing.expected_cash if (closing and closing.is_closed) else summary["expected_cash"]
    variance = closing.variance if (closing and closing.is_closed) else (counted_cash - expected_cash)

    # Recent closings (last 10)
    recent_closings = (
        db.query(CashClosing)
        .order_by(desc(CashClosing.date))
        .limit(10)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="cash/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "target_date": target_date,
            "today_ist": today_ist,
            "closing": closing,
            "is_closed": is_closed,
            "opening_cash": opening_cash,
            "counted_cash": counted_cash,
            "expected_cash": expected_cash,
            "variance": variance,
            "summary": summary,
            "recent_closings": recent_closings,
        },
    )


@router.get("/expected", response_class=HTMLResponse)
def cash_expected_live(
    request: Request,
    date_str: str = Query(..., alias="date"),
    opening: str = Query("0"),
    counted: str = Query("0"),
    db: Session = Depends(get_db),
):
    """HTMX endpoint to live recompute expected and variance upon input changes."""
    try:
        target_date = date.fromisoformat(date_str)
        op_cash = parse_money(opening)
        ct_cash = parse_money(counted)
    except Exception:
        return HTMLResponse('<div class="text-xs text-red-500">Invalid inputs</div>')

    summary = compute_day_cash_summary(db, target_date, op_cash)
    expected = summary["expected_cash"]
    variance = ct_cash - expected

    var_color = "text-emerald-600" if variance == 0 else ("text-red-600" if variance < 0 else "text-amber-600")

    return HTMLResponse(
        f'<div id="expected-cash-display" class="font-mono text-2xl font-extrabold text-slate-900" hx-swap-oob="true">{format_inr(expected)}</div>'
        f'<div id="variance-display" class="font-mono text-2xl font-extrabold {var_color}" hx-swap-oob="true">'
        f'{("+" if variance > 0 else "")}{format_inr(variance)}'
        f'</div>'
    )


@router.post("/{date_str}/close", dependencies=[Depends(verify_csrf)])
def cash_close_post(
    request: Request,
    date_str: str,
    opening_cash: str = Form(...),
    counted_cash: str = Form(...),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    try:
        target_date = date.fromisoformat(date_str)
        op = parse_money(opening_cash)
        ct = parse_money(counted_cash)
        close_cash_day(db, target_date, opening_cash=op, counted_cash=ct, note=note)
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url=f"/cash?date={date_str}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{date_str}/reopen", dependencies=[Depends(verify_csrf)])
def cash_reopen_post(
    request: Request,
    date_str: str,
    owner_pin: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        target_date = date.fromisoformat(date_str)
        reopen_cash_day(db, target_date, owner_pin=owner_pin)
        db.commit()
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url=f"/cash?date={date_str}", status_code=status.HTTP_303_SEE_OTHER)
