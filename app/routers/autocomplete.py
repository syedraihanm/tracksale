from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_login
from app.models.ticket import Ticket

router = APIRouter(prefix="/autocomplete", dependencies=[Depends(require_login)])


@router.get("/brands", response_class=HTMLResponse)
def autocomplete_brands(db: Session = Depends(get_db)) -> HTMLResponse:
    """Return distinct device brands previously used."""
    brands = (
        db.query(Ticket.device_brand)
        .filter(Ticket.is_deleted.is_(False))
        .distinct()
        .order_by(Ticket.device_brand.asc())
        .all()
    )
    # Deduplicate and strip any surrounding quotes or backslashes
    cleaned = sorted({b[0].strip().strip('\'"\\').strip() for b in brands if b[0] and b[0].strip().strip('\'"\\').strip()})
    options = "".join(f'<option value="{c}">' for c in cleaned)
    return HTMLResponse(content=options)


@router.get("/models", response_class=HTMLResponse)
def autocomplete_models(
    brand: str = Query("", max_length=60),
    device_brand: str = Query("", max_length=60),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Return distinct device models, optionally filtered by brand."""
    target_brand = (brand or device_brand).strip().strip('\'"\\').strip()
    query = db.query(Ticket.device_model).filter(Ticket.is_deleted.is_(False)).distinct()
    if target_brand:
        query = query.filter(Ticket.device_brand.ilike(target_brand))
    models = query.order_by(Ticket.device_model.asc()).all()
    cleaned = sorted({m[0].strip().strip('\'"\\').strip() for m in models if m[0] and m[0].strip().strip('\'"\\').strip()})
    options = "".join(f'<option value="{c}">' for c in cleaned)
    return HTMLResponse(content=options)
