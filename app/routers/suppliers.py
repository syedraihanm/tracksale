from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.formatting import parse_money
from app.models.settings import Settings as SettingsModel
from app.services.errors import ValidationFailed
from app.services.suppliers import (
    create_supplier,
    delete_supplier,
    delete_supplier_payment,
    get_all_suppliers_summary,
    get_supplier,
    get_supplier_ledger,
    record_supplier_payment,
    update_supplier,
)
from app.templating import templates

router = APIRouter(prefix="/suppliers", dependencies=[Depends(require_login)])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def suppliers_list_view(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
):
    """Suppliers directory and payment reconciliation overview."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    summary_data = get_all_suppliers_summary(db, search=q if q.strip() else None)

    context = {
        "request": request,
        "session": session,
        "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
        "suppliers_summary": summary_data["suppliers"],
        "total_suppliers": summary_data["total_suppliers"],
        "total_bought_all": summary_data["total_bought_all"],
        "total_paid_all": summary_data["total_paid_all"],
        "total_pending_all": summary_data["total_pending_all"],
        "search_query": q,
    }
    return templates.TemplateResponse(request=request, name="suppliers/index.html", context=context)


@router.post("", dependencies=[Depends(verify_csrf)])
@router.post("/", dependencies=[Depends(verify_csrf)])
def supplier_create(
    request: Request,
    name: str = Form(...),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    contact_person: str | None = Form(None),
    address: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Add a new supplier."""
    try:
        sup = create_supplier(
            db=db,
            name=name,
            phone=phone,
            email=email,
            contact_person=contact_person,
            address=address,
            notes=notes,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/suppliers/{sup.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{id}", response_class=HTMLResponse)
def supplier_detail_view(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
):
    """Supplier profile, purchase history, payment tracking, and ledger balance."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    try:
        ledger = get_supplier_ledger(db, id)
    except ValidationFailed:
        raise HTTPException(status_code=404, detail="Supplier not found")

    context = {
        "request": request,
        "session": session,
        "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
        "supplier": ledger["supplier"],
        "parts_purchased": ledger["parts_purchased"],
        "inventory_spares": ledger["inventory_spares"],
        "payments": ledger["payments"],
        "total_parts_bought": ledger["total_parts_bought"],
        "total_inventory_stock_value": ledger["total_inventory_stock_value"],
        "total_bought": ledger["total_bought"],
        "total_paid": ledger["total_paid"],
        "pending_payment": ledger["pending_payment"],
    }
    return templates.TemplateResponse(request=request, name="suppliers/detail.html", context=context)


@router.post("/{id}/edit", dependencies=[Depends(verify_csrf)])
def supplier_edit(
    request: Request,
    id: int,
    name: str = Form(...),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    contact_person: str | None = Form(None),
    address: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Edit supplier details."""
    sup = get_supplier(db, id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")

    try:
        update_supplier(
            db=db,
            supplier=sup,
            name=name,
            phone=phone,
            email=email,
            contact_person=contact_person,
            address=address,
            notes=notes,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/suppliers/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/delete", dependencies=[Depends(verify_csrf)])
def supplier_delete(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
):
    """Soft delete supplier."""
    sup = get_supplier(db, id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")

    try:
        delete_supplier(db=db, supplier=sup)
        db.commit()
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url="/suppliers", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/payments", dependencies=[Depends(verify_csrf)])
def supplier_record_payment(
    request: Request,
    id: int,
    amount: str = Form(...),
    mode: str = Form("cash"),
    reference: str | None = Form(None),
    notes: str | None = Form(None),
    paid_at: str | None = Form(None),
    redirect_to: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Record a payment made to a supplier."""
    sup = get_supplier(db, id)
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")

    try:
        amt = parse_money(amount)
        paid_dt = None
        if paid_at and paid_at.strip():
            paid_dt = datetime.fromisoformat(paid_at.strip())

        record_supplier_payment(
            db=db,
            supplier=sup,
            amount=amt,
            mode=mode,
            reference=reference,
            notes=notes,
            paid_at=paid_dt,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    dest = redirect_to if redirect_to and redirect_to.startswith("/suppliers") else f"/suppliers/{id}"
    return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/payments/{payment_id}/delete", dependencies=[Depends(verify_csrf)])
def supplier_payment_delete(
    request: Request,
    payment_id: int,
    reason: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Void / soft-delete a recorded supplier payment."""
    from app.models.supplier import SupplierPayment

    pmt = db.query(SupplierPayment).filter_by(id=payment_id, is_deleted=False).first()
    if not pmt:
        raise HTTPException(status_code=404, detail="Payment not found")

    sup_id = pmt.supplier_id
    try:
        delete_supplier_payment(db=db, payment=pmt, reason=reason)
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/suppliers/{sup_id}", status_code=status.HTTP_303_SEE_OTHER)
