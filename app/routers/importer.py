import csv
import io

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_session, require_login, require_pin_unlock, verify_csrf
from app.models.settings import Settings as SettingsModel
from app.services.importer import extract_rows_from_file, process_import
from app.templating import templates

router = APIRouter(prefix="/import", dependencies=[Depends(require_login), Depends(require_pin_unlock)])

# Temporary cache for parsed file session
UPLOAD_CACHE: dict[str, dict] = {}


@router.get("", response_class=HTMLResponse)
def import_page(request: Request, db: Session = Depends(get_db)):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    return templates.TemplateResponse(
        request=request,
        name="importer/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "step": "upload",
        },
    )


@router.post("/upload")
async def import_upload(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 5 MB limit")

    headers, data_rows = extract_rows_from_file(file_bytes, file.filename or "import.csv")
    if not headers or not data_rows:
        return templates.TemplateResponse(
            request=request,
            name="importer/index.html",
            context={
                "session": session,
                "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
                "step": "upload",
                "error": "The uploaded file is empty or could not be parsed.",
            },
            status_code=422,
        )

    user_key = session.get("user_id", "admin")
    UPLOAD_CACHE[user_key] = {
        "headers": headers,
        "data_rows": data_rows,
        "filename": file.filename,
    }

    # Best-guess automatic mapping
    auto_mapping = {}
    lower_headers = {h.lower(): h for h in headers}

    candidates = {
        "phone": ["phone", "mobile", "contact", "customer phone", "cell"],
        "customer_name": ["name", "customer", "customer name", "client"],
        "device_brand": ["brand", "make", "manufacturer"],
        "device_model": ["model", "device", "handset", "phone model"],
        "reported_issue": ["issue", "problem", "fault", "complaint", "repair"],
        "received_date": ["received date", "date received", "intake date", "date"],
        "delivered_date": ["delivered date", "date delivered", "delivery date", "completed"],
        "amount": ["amount", "price", "charge", "cost", "total"],
        "payment_mode": ["mode", "payment mode", "payment type", "payment method"],
    }

    for field, terms in candidates.items():
        for term in terms:
            if term in lower_headers:
                auto_mapping[field] = lower_headers[term]
                break

    return templates.TemplateResponse(
        request=request,
        name="importer/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "step": "mapping",
            "headers": headers,
            "total_rows": len(data_rows),
            "filename": file.filename,
            "auto_mapping": auto_mapping,
        },
    )


@router.post("/preview")
def import_preview(
    request: Request,
    phone_col: str = Form(...),
    name_col: str = Form(...),
    brand_col: str = Form(...),
    model_col: str = Form(...),
    issue_col: str = Form(...),
    received_col: str | None = Form(None),
    delivered_col: str | None = Form(None),
    amount_col: str | None = Form(None),
    mode_col: str | None = Form(None),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    setting = db.query(SettingsModel).filter_by(id=1).first()
    user_key = session.get("user_id", "admin")

    cached = UPLOAD_CACHE.get(user_key)
    if not cached:
        return RedirectResponse(url="/import", status_code=303)

    mapping = {
        "phone": phone_col,
        "customer_name": name_col,
        "device_brand": brand_col,
        "device_model": model_col,
        "reported_issue": issue_col,
        "received_date": received_col or "",
        "delivered_date": delivered_col or "",
        "amount": amount_col or "",
        "payment_mode": mode_col or "",
    }
    cached["mapping"] = mapping

    result = process_import(
        db=db,
        headers=cached["headers"],
        data_rows=cached["data_rows"],
        mapping=mapping,
        dry_run=True,
    )
    cached["last_result"] = result

    return templates.TemplateResponse(
        request=request,
        name="importer/index.html",
        context={
            "session": session,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "step": "preview",
            "result": result,
            "mapping": mapping,
            "filename": cached["filename"],
        },
    )


@router.post("/commit", dependencies=[Depends(verify_csrf)])
def import_commit(request: Request, db: Session = Depends(get_db)):
    session = get_current_session(request)
    user_key = session.get("user_id", "admin")
    cached = UPLOAD_CACHE.get(user_key)
    if not cached or "mapping" not in cached:
        return RedirectResponse(url="/import", status_code=303)

    result = process_import(
        db=db,
        headers=cached["headers"],
        data_rows=cached["data_rows"],
        mapping=cached["mapping"],
        dry_run=False,
    )

    return templates.TemplateResponse(
        request=request,
        name="importer/index.html",
        context={
            "session": session,
            "step": "complete",
            "result": result,
        },
    )


@router.get("/errors.csv")
def download_errors_csv(request: Request):
    session = get_current_session(request)
    user_key = session.get("user_id", "admin")
    cached = UPLOAD_CACHE.get(user_key)
    if not cached or "last_result" not in cached:
        raise HTTPException(status_code=404, detail="No error report available")

    errors = cached["last_result"].get("errors", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Row Number", "Error Reason", "Raw Data"])
    for e in errors:
        writer.writerow([e["row_num"], e["error"], " | ".join(e["data"])])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=import_errors.csv"},
    )
