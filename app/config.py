from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and ("dev-insecure" in settings.SECRET_KEY or len(settings.SECRET_KEY) < 16):
        raise ValueError("SECRET_KEY must be securely configured in production")
    return settings
