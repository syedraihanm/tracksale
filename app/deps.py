from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Response, status

from app.security import (
    PIN_UNLOCK_MAX_AGE,
    decode_session,
    encode_session,
)


def get_current_session(request: Request) -> dict | None:
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    data = decode_session(cookie)
    return data


def require_login(request: Request) -> dict:
    session = get_current_session(request)
    if not session or not session.get("user_id"):
        # Check if HTMX request
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"HX-Redirect": f"/login?next={request.url.path}"},
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/login?next={request.url.path}"},
        )
    return session


async def verify_csrf(request: Request, session: dict = Depends(require_login)) -> None:
    """Verify CSRF token for mutating requests (POST, PUT, DELETE, PATCH)."""
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        token_from_header = request.headers.get("X-CSRF-Token")
        token_from_form = None
        if not token_from_header:
            try:
                form = await request.form()
                token_from_form = form.get("csrf_token")
            except Exception:
                token_from_form = None
        submitted_token = token_from_header or token_from_form
        expected_token = session.get("csrf_token")

        if not submitted_token or submitted_token != expected_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed",
            )


def require_pin_unlock(request: Request, response: Response, session: dict = Depends(require_login)) -> dict:
    """Check sliding 15-minute PIN unlock status."""
    pin_unlocked_at = session.get("pin_unlocked_at")
    now = datetime.now(UTC).timestamp()

    if not pin_unlocked_at or (now - pin_unlocked_at > PIN_UNLOCK_MAX_AGE):
        # Locked -> redirect to PIN page
        if request.headers.get("HX-Request") == "true":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"HX-Redirect": f"/pin?next={request.url.path}"},
            )
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/pin?next={request.url.path}"},
        )

    # Slide window
    session["pin_unlocked_at"] = now
    new_token = encode_session(session)
    response.set_cookie(
        key="session",
        value=new_token,
        max_age=43200,
        httponly=True,
        samesite="lax",
    )
    return session
