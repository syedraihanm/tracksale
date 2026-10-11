
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_login, verify_csrf
from app.formatting import parse_money
from app.models.ticket import Ticket
from app.models.ticket_item import TicketItem
from app.services.errors import PinRequired, ValidationFailed
from app.services.items import add_item, delete_item, edit_item

router = APIRouter(dependencies=[Depends(require_login), Depends(verify_csrf)])


@router.post("/tickets/{id}/items")
def route_add_item(
    request: Request,
    id: int,
    item_type: str = Form(...),
    description: str = Form(...),
    price_charged: str = Form(...),
    cost_price: str = Form("0"),
    supplier_name: str | None = Form(None),
    owner_pin: str | None = Form(None),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        price = parse_money(price_charged)
        cost = parse_money(cost_price)
        add_item(
            db=db,
            ticket=ticket,
            item_type=item_type,
            description=description,
            price_charged=price,
            cost_price=cost,
            supplier_name=supplier_name,
            owner_pin=owner_pin,
        )
        db.commit()
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/{id}")
def route_edit_item(
    request: Request,
    id: int,
    description: str = Form(...),
    price_charged: str = Form(...),
    cost_price: str = Form("0"),
    supplier_name: str | None = Form(None),
    owner_pin: str | None = Form(None),
    db: Session = Depends(get_db),
):
    item = db.query(TicketItem).filter_by(id=id, is_deleted=False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    try:
        price = parse_money(price_charged)
        cost = parse_money(cost_price)
        edit_item(
            db=db,
            item=item,
            description=description,
            price_charged=price,
            cost_price=cost,
            supplier_name=supplier_name,
            owner_pin=owner_pin,
        )
        db.commit()
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{item.ticket_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/{id}/delete")
def route_delete_item(
    request: Request,
    id: int,
    owner_pin: str | None = Form(None),
    db: Session = Depends(get_db),
):
    item = db.query(TicketItem).filter_by(id=id, is_deleted=False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    ticket_id = item.ticket_id
    try:
        delete_item(db=db, item=item, owner_pin=owner_pin)
        db.commit()
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=status.HTTP_303_SEE_OTHER)
