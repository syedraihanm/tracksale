
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_login, verify_csrf
from app.formatting import parse_money
from app.models.payment import Payment
from app.models.ticket import Ticket
from app.services.errors import (
    DayClosed,
    NeedsConfirmation,
    PinRequired,
    ValidationFailed,
)
from app.services.payments import add_payment, delete_payment, edit_payment

router = APIRouter(dependencies=[Depends(require_login), Depends(verify_csrf)])


@router.post("/tickets/{id}/payments")
def route_add_payment(
    request: Request,
    id: int,
    amount: str = Form(...),
    mode: str = Form(...),
    kind: str = Form(...),
    note: str | None = Form(None),
    confirm_overpay: str | None = Form("0"),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).filter_by(id=id, is_deleted=False).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        parsed_amount = parse_money(amount)
        add_payment(
            db=db,
            ticket=ticket,
            amount=parsed_amount,
            mode=mode,
            kind=kind,
            note=note,
            confirm_overpay=confirm_overpay == "1",
        )
        db.commit()
    except NeedsConfirmation as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DayClosed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/payments/{id}")
def route_edit_payment(
    request: Request,
    id: int,
    amount: str = Form(...),
    mode: str = Form(...),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter_by(id=id, is_deleted=False).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    ticket_id = payment.ticket_id
    try:
        parsed_amount = parse_money(amount)
        edit_payment(
            db=db,
            payment=payment,
            amount=parsed_amount,
            mode=mode,
            note=note,
        )
        db.commit()
    except DayClosed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/payments/{id}/delete")
def route_delete_payment(
    request: Request,
    id: int,
    reason: str = Form(...),
    owner_pin: str = Form(...),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter_by(id=id, is_deleted=False).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    ticket_id = payment.ticket_id
    try:
        delete_payment(
            db=db,
            payment=payment,
            reason=reason,
            owner_pin=owner_pin,
        )
        db.commit()
    except DayClosed as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PinRequired as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (ValidationFailed, ValueError) as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=status.HTTP_303_SEE_OTHER)
