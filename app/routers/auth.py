from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_session
from app.models.settings import Settings as SettingsModel
from app.security import (
    create_session_data,
    encode_session,
    hash_secret,
    pin_limiter,
    verify_secret,
)
from app.services.audit import record_audit
from app.templating import templates

router = APIRouter()
settings = get_settings()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request, db: Session = Depends(get_db)):
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if setting and setting.setup_completed:
        raise HTTPException(status_code=404, detail="Setup already completed")
    return templates.TemplateResponse(
        request=request,
        name="auth/setup.html",
        context={"shop_name": setting.shop_name if setting else "Mobile Repair Shop"},
    )


@router.post("/setup")
def setup_post(
    request: Request,
    response: Response,
    shop_name: str = Form(...),
    shop_pin: str = Form(...),
    db: Session = Depends(get_db),
):
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if setting and setting.setup_completed:
        raise HTTPException(status_code=404, detail="Setup already completed")

    shop_name = shop_name.strip()
    if not shop_name or len(shop_name) > 100:
        return templates.TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={"error": "Shop name must be between 1 and 100 characters"},
            status_code=422,
        )

    shop_pin = shop_pin.strip()
    if not (shop_pin.isdigit() and 4 <= len(shop_pin) <= 6):
        return templates.TemplateResponse(
            request=request,
            name="auth/setup.html",
            context={"error": "Shop PIN must be 4 to 6 numeric digits"},
            status_code=422,
        )

    if not setting:
        setting = SettingsModel(id=1)
        db.add(setting)

    setting.shop_name = shop_name
    shared_pin_hash = hash_secret(shop_pin)
    setting.admin_password_hash = shared_pin_hash
    setting.owner_pin_hash = shared_pin_hash
    setting.setup_completed = True
    db.commit()

    # The submitted Shop PIN also authorizes Owner PIN actions for this session.
    session_data = create_session_data(user_id="admin")
    session_data["pin_unlocked_at"] = datetime.now(UTC).timestamp()
    token = encode_session(session_data)

    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key="session",
        value=token,
        max_age=43200,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )
    return resp


@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request, next: str = "/", db: Session = Depends(get_db)):
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if setting and not setting.setup_completed:
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "next_url": next,
            "shop_name": setting.shop_name if setting else "Mobile Repair Shop",
            "error": None,
        },
    )


@router.post("/login")
def login_post(
    request: Request,
    response: Response,
    pin: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    submitted_pin = (pin or password).strip()
    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting or not (setting.admin_password_hash or setting.owner_pin_hash):
        return RedirectResponse(url="/setup", status_code=status.HTTP_303_SEE_OTHER)

    admin_pin_matches = verify_secret(setting.admin_password_hash, submitted_pin)
    owner_pin_matches = verify_secret(setting.owner_pin_hash, submitted_pin)
    if not (admin_pin_matches or owner_pin_matches):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"next_url": next, "shop_name": setting.shop_name, "error": "Incorrect Shop PIN."},
            status_code=401,
        )

    owner_actions_unlocked = owner_pin_matches
    # Accept either credential once for upgrades from the former two-field setup,
    # then keep both existing hashes aligned when the submitted credential is a PIN.
    if submitted_pin.isdigit() and 4 <= len(submitted_pin) <= 6 and not (admin_pin_matches and owner_pin_matches):
        shared_pin_hash = hash_secret(submitted_pin)
        setting.admin_password_hash = shared_pin_hash
        setting.owner_pin_hash = shared_pin_hash
        current_time = datetime.now(UTC)
        setting.updated_at = current_time
        record_audit(
            db=db,
            entity="settings",
            entity_id=1,
            action="update",
            changed_fields={"shop_pin": {"changed": True}},
            reason="Legacy sign-in and Owner PIN credentials synchronized",
            now=current_time,
        )
        db.commit()
        owner_actions_unlocked = True

    session_data = create_session_data(user_id="admin")
    if owner_actions_unlocked:
        session_data["pin_unlocked_at"] = datetime.now(UTC).timestamp()
    token = encode_session(session_data)

    target_url = next if next.startswith("/") else "/"
    resp = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key="session",
        value=token,
        max_age=43200,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )
    return resp


@router.post("/logout")
def logout_post(request: Request):
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("session")
    return resp


@router.get("/pin", response_class=HTMLResponse)
def pin_get(request: Request, next: str = "/"):
    session = get_current_session(request)
    if not session or not session.get("user_id"):
        return RedirectResponse(url=f"/login?next=/pin?next={next}", status_code=status.HTTP_303_SEE_OTHER)

    client_ip = get_client_ip(request)
    locked, remaining = pin_limiter.is_locked(client_ip)
    error = None
    if locked:
        error = f"Too many failed PIN attempts. Locked for {remaining} seconds."

    return templates.TemplateResponse(
        request=request,
        name="auth/pin.html",
        context={
            "session": session,
            "next_url": next,
            "error": error,
        },
    )


@router.post("/pin")
def pin_post(
    request: Request,
    response: Response,
    pin: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    session = get_current_session(request)
    if not session or not session.get("user_id"):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    client_ip = get_client_ip(request)
    locked, remaining = pin_limiter.is_locked(client_ip)
    if locked:
        return templates.TemplateResponse(
            request=request,
            name="auth/pin.html",
            context={
                "session": session,
                "next_url": next,
                "error": f"Too many failed PIN attempts. Locked for {remaining} seconds.",
            },
            status_code=429,
        )

    setting = db.query(SettingsModel).filter_by(id=1).first()
    if not setting or not setting.owner_pin_hash or not verify_secret(setting.owner_pin_hash, pin.strip()):
        locked_now, lock_duration = pin_limiter.record_failure(client_ip)
        msg = f"Too many failed PIN attempts. Locked for {lock_duration} seconds." if locked_now else "Incorrect Owner PIN."
        status_code = 429 if locked_now else 403
        return templates.TemplateResponse(
            request=request,
            name="auth/pin.html",
            context={"session": session, "next_url": next, "error": msg},
            status_code=status_code,
        )

    pin_limiter.record_success(client_ip)
    session["pin_unlocked_at"] = datetime.now(UTC).timestamp()
    token = encode_session(session)

    target_url = next if next.startswith("/") else "/"
    resp = RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key="session",
        value=token,
        max_age=43200,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )
    return resp

