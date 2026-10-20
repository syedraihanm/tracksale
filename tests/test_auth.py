import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.settings import Settings as SettingsModel
from app.security import (
    decrypt_passcode,
    encrypt_passcode,
    hash_secret,
    pin_limiter,
)


@pytest.fixture
def client(temp_db):
    def override_get_db():
        try:
            yield temp_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # Reset limiters for tests
    pin_limiter.attempts.clear()
    pin_limiter.lockouts.clear()

    with TestClient(app, follow_redirects=False) as c:
        yield c

    app.dependency_overrides.clear()


def test_security_headers(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert res.headers["Referrer-Policy"] == "same-origin"


def test_setup_flow(client, temp_db):
    # GET /setup when setup_completed is False
    res = client.get("/setup")
    assert res.status_code == 200

    # Validation: Shop PIN must contain 4 to 6 digits
    res = client.post("/setup", data={"shop_name": "Test Shop", "shop_pin": "12"})
    assert res.status_code == 422

    # Validation: non-numeric PIN
    res = client.post("/setup", data={"shop_name": "Test Shop", "shop_pin": "abcd"})
    assert res.status_code == 422

    # Valid setup
    res = client.post(
        "/setup",
        data={"shop_name": "My Master Repair", "shop_pin": "9999"},
    )
    assert res.status_code == 303
    assert "session" in res.cookies

    # GET /setup now returns 404
    res2 = client.get("/setup")
    assert res2.status_code == 404


def test_login_does_not_apply_a_300_second_lockout(client, temp_db):
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.admin_password_hash = hash_secret("correct_password_123")
    setting.setup_completed = True
    temp_db.commit()

    # Repeated failed sign-ins stay available; there is no 300-second password lockout.
    for _ in range(6):
        res = client.post("/login", data={"password": "wrong_password"})
        assert res.status_code == 401

    res_ok = client.post("/login", data={"password": "correct_password_123"})
    assert res_ok.status_code == 303
    assert "session" in res_ok.cookies


def test_passcode_encryption():
    plain = "Unlock1234"
    cipher = encrypt_passcode(plain)
    assert cipher != plain
    assert decrypt_passcode(cipher) == plain
    assert decrypt_passcode(None) is None


def test_route_aliases(client, temp_db):
    # Test health endpoints
    res_z = client.get("/healthz")
    assert res_z.status_code == 200
    assert res_z.json() == {"status": "ok", "db": "ok"}

    res_h = client.get("/health")
    assert res_h.status_code == 200
    assert res_h.json() == {"status": "ok", "db": "ok"}

    # Set up user and log in
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.admin_password_hash = hash_secret("secret123")
    setting.setup_completed = True
    temp_db.commit()

    # Unauthenticated redirects to /login
    assert client.get("/").status_code == 303
    assert client.get("/queue").status_code == 303

    # Log in
    login_res = client.post("/login", data={"password": "secret123"})
    assert login_res.status_code == 303
    client.cookies.set("session", login_res.cookies["session"])

    # Both / and /queue return 200 for authenticated sessions
    res_root = client.get("/")
    assert res_root.status_code == 200

    res_queue = client.get("/queue")
    assert res_queue.status_code == 200


def test_independent_rate_limiters():
    from app.security import RateLimiter

    login_rl = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=60)
    pin_rl = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=60)

    key = "127.0.0.1"

    # Fail login 3 times -> login locks out
    login_rl.record_failure(key)
    login_rl.record_failure(key)
    locked, remaining = login_rl.record_failure(key)
    assert locked is True
    assert remaining > 0

    # PIN rate limiter for same IP must NOT be locked
    is_pin_locked, _ = pin_rl.is_locked(key)
    assert is_pin_locked is False

