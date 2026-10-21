"""Vercel-specific database initialization helpers."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.db import engine

_MIGRATION_LOCK_ID = 581_031_420_267


def upgrade_database() -> None:
    """Apply Alembic migrations once, serializing concurrent cold starts."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Vercel deployment requires a persistent PostgreSQL DATABASE_URL.")

    project_root = Path(__file__).resolve().parent.parent
    alembic_config = Config(str(project_root / "alembic.ini"))

    # Transaction-scoped locks also work with pooled PostgreSQL endpoints, which
    # may use transaction pooling between application and database connections.
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _MIGRATION_LOCK_ID})
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
