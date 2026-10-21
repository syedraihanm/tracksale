from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_session, require_login, verify_csrf
from app.models.settings import Settings as SettingsModel
from app.services.backup import create_backup, list_backups
from app.services.errors import PinRequired, ValidationFailed
from app.services.settings_service import (
    change_owner_pin,
    change_password,
    update_receipt_and_templates,
    update_shop_details,
)
from app.templating import templates

router = APIRouter(prefix="/settings", dependencies=[Depends(require_login)])
app_settings = get_settings()


@router.get("", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()
    backups = list_backups()

    return templates.TemplateResponse(
        request=request,
        name="settings/index.html",
        context={
            "session": session,
            "setting": setting,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "backups": backups,
            "is_hosted_database": not app_settings.uses_sqlite,
        },
    )


@router.post("/backup/run", dependencies=[Depends(verify_csrf)])
@router.post("/backup-now", dependencies=[Depends(verify_csrf)], include_in_schema=False)
def run_backup_now():
    if app_settings.is_vercel or not app_settings.uses_sqlite:
        raise HTTPException(status_code=404, detail="File backups are not available for hosted PostgreSQL shops")
    try:
        create_backup()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/backup/download")
def download_backup(filename: str = Query(...)):
    if app_settings.is_vercel or not app_settings.uses_sqlite:
        raise HTTPException(status_code=404, detail="File backups are not available for hosted PostgreSQL shops")
    # Validate filename to prevent path traversal
    safe_name = Path(filename).name
    target_path = app_settings.backup_path / safe_name
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=str(target_path),
        filename=safe_name,
        media_type="application/x-sqlite3",
    )


@router.post("/shop", dependencies=[Depends(verify_csrf)])
def post_shop_details(
    request: Request,
    shop_name: str = Form(...),
    shop_phone: str = Form(""),
    shop_address: str = Form(""),
    default_warranty_days: int = Form(30),
    ticket_no_prefix: str = Form("R"),
    db: Session = Depends(get_db),
):
    try:
        update_shop_details(
            db=db,
            shop_name=shop_name,
            shop_phone=shop_phone,
            shop_address=shop_address,
            default_warranty_days=default_warranty_days,
            ticket_no_prefix=ticket_no_prefix,
        )
        db.commit()
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/templates", dependencies=[Depends(verify_csrf)])
def post_templates(
    request: Request,
    receipt_terms_text: str = Form(...),
    msg_template_intake: str = Form(...),
    msg_template_ready: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        update_receipt_and_templates(
            db=db,
            receipt_terms_text=receipt_terms_text,
            msg_template_intake=msg_template_intake,
            msg_template_ready=msg_template_ready,
        )
        db.commit()
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/password", dependencies=[Depends(verify_csrf)])
def post_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        change_password(db=db, current_password=current_password, new_password=new_password)
        db.commit()
    except ValidationFailed as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/pin", dependencies=[Depends(verify_csrf)])
def post_change_pin(
    request: Request,
    current_pin: str = Form(...),
    new_pin: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        change_owner_pin(db=db, current_pin=current_pin, new_pin=new_pin)
        db.commit()
    except (PinRequired, ValidationFailed) as e:
        db.rollback()
        raise HTTPException(status_code=403 if isinstance(e, PinRequired) else 422, detail=str(e))

    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)
