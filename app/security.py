import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

ph = PasswordHasher()
settings = get_settings()
serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

# Fernet cipher instance
try:
    fernet = Fernet(settings.PASSCODE_ENCRYPTION_KEY.encode())
except Exception:
    # If invalid key format, generate a fallback for dev
    fernet = Fernet(Fernet.generate_key())


def hash_secret(secret: str) -> str:
    """Hash password or PIN using Argon2id."""
    return ph.hash(secret)


def verify_secret(secret_hash: str, secret: str) -> bool:
    """Verify password or PIN against Argon2 hash."""
    if not secret_hash:
        return False
    try:
        return ph.verify(secret_hash, secret)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def encrypt_passcode(plain: str | None) -> str | None:
    """Encrypt device passcode using Fernet."""
    if not plain:
        return None
    return fernet.encrypt(plain.encode()).decode()


def decrypt_passcode(cipher: str | None) -> str | None:
    """Decrypt device passcode using Fernet."""
    if not cipher:
        return None
    try:
        return fernet.decrypt(cipher.encode()).decode()
    except (InvalidToken, Exception):
        return "[Decryption failed]"


# Rate Limiting
class RateLimiter:
    """In-memory rate limiter: 5 failures in 5 min -> 5 min lockout."""
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.attempts: dict[str, list[float]] = {}
        self.lockouts: dict[str, float] = {}

    def _prune_expired(self, now: float) -> None:
        cutoff = now - self.window_seconds
        # Clean expired lockouts
        expired_lockouts = [k for k, v in self.lockouts.items() if v <= now]
        for k in expired_lockouts:
            self.lockouts.pop(k, None)
            self.attempts.pop(k, None)

        # Clean empty or stale attempt buckets
        stale_keys = [k for k, v in self.attempts.items() if not [t for t in v if t > cutoff]]
        for k in stale_keys:
            self.attempts.pop(k, None)

        # Bound maximum tracked keys to 1,000
        if len(self.attempts) > 1000:
            excess = len(self.attempts) - 1000
            for k in list(self.attempts.keys())[:excess]:
                self.attempts.pop(k, None)
        if len(self.lockouts) > 1000:
            excess = len(self.lockouts) - 1000
            for k in list(self.lockouts.keys())[:excess]:
                self.lockouts.pop(k, None)

    def is_locked(self, key: str, now_ts: float | None = None) -> tuple[bool, int]:
        now = now_ts or datetime.now(UTC).timestamp()
        self._prune_expired(now)
        locked_until = self.lockouts.get(key)
        if locked_until:
            if now < locked_until:
                remaining = int(locked_until - now) + 1
                return True, remaining
            else:
                self.lockouts.pop(key, None)
                self.attempts[key] = []
        return False, 0

    def record_failure(self, key: str, now_ts: float | None = None) -> tuple[bool, int]:
        now = now_ts or datetime.now(UTC).timestamp()
        self._prune_expired(now)
        cutoff = now - self.window_seconds
        current = [t for t in self.attempts.get(key, []) if t > cutoff]
        current.append(now)
        self.attempts[key] = current

        if len(current) >= self.max_attempts:
            lock_until = now + self.lockout_seconds
            self.lockouts[key] = lock_until
            return True, self.lockout_seconds
        return False, 0

    def record_success(self, key: str):
        self.attempts.pop(key, None)
        self.lockouts.pop(key, None)


login_limiter = RateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=300)
pin_limiter = RateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=300)


# Session & CSRF helpers
SESSION_MAX_AGE = 43200  # 12 hours in seconds
PIN_UNLOCK_MAX_AGE = 900  # 15 minutes sliding


def create_session_data(user_id: str = "admin") -> dict:
    return {
        "user_id": user_id,
        "csrf_token": secrets.token_urlsafe(32),
        "pin_unlocked_at": None,
    }


def encode_session(data: dict) -> str:
    return serializer.dumps(data)


def decode_session(token: str) -> dict | None:
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data
    except (BadSignature, SignatureExpired, Exception):
        return None
