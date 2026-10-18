from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.formatting import parse_money
from app.models.enums import SPARE_CATEGORIES
from app.models.inventory import InventoryItem
from app.models.settings import Settings as SettingsModel
from app.services.errors import ValidationFailed
from app.services.inventory import (
    add_inventory_item,
    adjust_inventory_stock,
    delete_inventory_item,
    edit_inventory_item,
    get_inventory_item,
    list_inventory,
)
from app.templating import templates

router = APIRouter(prefix="/inventory", dependencies=[Depends(require_login)])


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def inventory_list_view(
    request: Request,
    q: str = "",
    category: str = "all",
    db: Session = Depends(get_db),
):
    """Inventory dashboard and management page."""
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    all_items = db.query(InventoryItem).filter(InventoryItem.is_deleted.is_(False)).all()

    # Metrics
    total_spares = len(all_items)
    total_quantity = sum(item.quantity for item in all_items)
    low_stock = sum(1 for item in all_items if 0 < item.quantity <= 2)
    out_of_stock = sum(1 for item in all_items if item.quantity == 0)

    # Filtered list
    filtered_items = list_inventory(
        db=db,
        search=q if q.strip() else None,
        spare_type=category if category != "all" else None,
    )

    from app.services.suppliers import list_suppliers
    suppliers = list_suppliers(db, active_only=True)

    context = {
        "request": request,
        "session": session,
        "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
        "items": filtered_items,
        "total_spares": total_spares,
        "total_quantity": total_quantity,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "categories": SPARE_CATEGORIES,
        "selected_category": category,
        "search_query": q,
        "suppliers": suppliers,
    }

    return templates.TemplateResponse(request=request, name="inventory/index.html", context=context)


@router.post("", dependencies=[Depends(verify_csrf)])
@router.post("/", dependencies=[Depends(verify_csrf)])
def route_add_inventory_item(
    request: Request,
    spare_type: str = Form(...),
    model: str = Form(...),
    quantity: str = Form("1"),
    cost_price: str = Form("0"),
    selling_price: str = Form("0"),
    supplier_name: str | None = Form(None),
    supplier_id: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Add a new spare part to inventory."""
    try:
        qty = int(quantity.strip()) if quantity.strip() else 1
        cost = parse_money(cost_price)
        sell = parse_money(selling_price)
        sup_id = int(supplier_id.strip()) if (supplier_id and supplier_id.strip().isdigit()) else None
        add_inventory_item(
            db=db,
            spare_type=spare_type,
            model=model,
            quantity=qty,
            cost_price=cost,
            selling_price=sell,
            supplier_name=supplier_name,
            supplier_id=sup_id,
            notes=notes,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/edit", dependencies=[Depends(verify_csrf)])
def route_edit_inventory_item(
    request: Request,
    id: int,
    spare_type: str = Form(...),
    model: str = Form(...),
    quantity: str = Form(...),
    cost_price: str = Form("0"),
    selling_price: str = Form("0"),
    supplier_name: str | None = Form(None),
    supplier_id: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Edit spare part details."""
    item = get_inventory_item(db, id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    try:
        qty = int(quantity.strip()) if quantity.strip() else 0
        cost = parse_money(cost_price)
        sell = parse_money(selling_price)
        sup_id = int(supplier_id.strip()) if (supplier_id and supplier_id.strip().isdigit()) else None
        edit_inventory_item(
            db=db,
            item=item,
            spare_type=spare_type,
            model=model,
            quantity=qty,
            cost_price=cost,
            selling_price=sell,
            supplier_name=supplier_name,
            supplier_id=sup_id,
            notes=notes,
        )
        db.commit()
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/stock", dependencies=[Depends(verify_csrf)])
def route_adjust_stock(
    request: Request,
    id: int,
    delta: int = Form(...),
    reason: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Quick stock increment/decrement."""
    item = get_inventory_item(db, id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    try:
        adjust_inventory_stock(db, item, delta=delta, reason=reason)
        db.commit()
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{id}/delete", dependencies=[Depends(verify_csrf)])
def route_delete_inventory_item(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
):
    """Soft delete an inventory item."""
    item = get_inventory_item(db, id)
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    delete_inventory_item(db, item)
    db.commit()
    return RedirectResponse(url="/inventory", status_code=status.HTTP_303_SEE_OTHER)
