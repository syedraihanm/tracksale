from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_KEYS: set[str] = {
    "change-this-in-production-use-scripts-gen-key-py",
    "dev-insecure-secret-key-must-override-in-prod-12345678",
    "PH_13btabNyspTjWnDstwe9GTl3rMAEREI71jCXTQbA=",
}


class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-insecure-secret-key-must-override-in-prod-12345678"
    PASSCODE_ENCRYPTION_KEY: str = "PH_13btabNyspTjWnDstwe9GTl3rMAEREI71jCXTQbA="
    DATABASE_URL: str = "sqlite:///data/shop.db"
    BACKUP_DIR: str = "backups"
    COOKIE_SECURE: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def backup_path(self) -> Path:
        p = Path(self.BACKUP_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        try:
            Fernet(self.PASSCODE_ENCRYPTION_KEY.encode())
        except Exception as e:
            raise ValueError(
                "PASSCODE_ENCRYPTION_KEY must be a valid 32-byte urlsafe base64 Fernet key. Run: uv run python scripts/gen_key.py"
            ) from e

        if self.is_production:
            if (
                len(self.SECRET_KEY) < 32
                or self.SECRET_KEY in INSECURE_DEFAULT_KEYS
                or "dev-insecure" in self.SECRET_KEY
            ):
                raise ValueError("Production requires a strong SECRET_KEY (>= 32 chars) not matching default/example keys.")
            if self.PASSCODE_ENCRYPTION_KEY in INSECURE_DEFAULT_KEYS:
                raise ValueError("Production requires a unique PASSCODE_ENCRYPTION_KEY not matching default/example keys.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
