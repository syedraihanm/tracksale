import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.settings import Settings as SettingsModel
from app.security import (
    decrypt_passcode,
    encrypt_passcode,
    hash_secret,
    login_limiter,
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
    login_limiter.attempts.clear()
    login_limiter.lockouts.clear()
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

    # Validation: short password
    res = client.post("/setup", data={"shop_name": "Test Shop", "password": "short", "owner_pin": "1234"})
    assert res.status_code == 422

    # Validation: invalid PIN length
    res = client.post("/setup", data={"shop_name": "Test Shop", "password": "validpassword123", "owner_pin": "12"})
    assert res.status_code == 422

    # Valid setup
    res = client.post(
        "/setup",
        data={"shop_name": "My Master Repair", "password": "securepassword123", "owner_pin": "9999"},
    )
    assert res.status_code == 303
    assert "session" in res.cookies

    # GET /setup now returns 404
    res2 = client.get("/setup")
    assert res2.status_code == 404


def test_login_and_rate_limiting(client, temp_db):
    setting = temp_db.query(SettingsModel).filter_by(id=1).first()
    setting.admin_password_hash = hash_secret("correct_password_123")
    setting.setup_completed = True
    temp_db.commit()

    # Fail 5 times
    for _ in range(5):
        res = client.post("/login", data={"password": "wrong_password"})
        assert res.status_code in (401, 429)

    # 6th attempt is locked
    res_locked = client.post("/login", data={"password": "wrong_password"})
    assert res_locked.status_code == 429
    assert "Too many failed attempts" in res_locked.text

    # Clear rate limiter to test success
    login_limiter.attempts.clear()
    login_limiter.lockouts.clear()

    res_ok = client.post("/login", data={"password": "correct_password_123"})
    assert res_ok.status_code == 303
    assert "session" in res_ok.cookies


def test_passcode_encryption():
    plain = "Unlock1234"
    cipher = encrypt_passcode(plain)
    assert cipher != plain
    assert decrypt_passcode(cipher) == plain
    assert decrypt_passcode(None) is None
