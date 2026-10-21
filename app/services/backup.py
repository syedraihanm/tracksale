import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.timeutil import IST, to_ist, utc_now

logger = logging.getLogger("repair_shop.backup")
settings = get_settings()


def get_sqlite_source_path() -> Path:
    if settings.DATABASE_URL.startswith("sqlite:///"):
        path_str = settings.DATABASE_URL.replace("sqlite:///", "")
        return Path(path_str)
    return Path("data/shop.db")


def create_backup(now_dt: datetime | None = None, src_path: Path | None = None, backup_dir: Path | None = None) -> Path:
    """Create an online SQLite backup using sqlite3.backup() and prune older than 30."""
    if not settings.uses_sqlite:
        raise RuntimeError(
            "File backups are available only for local SQLite databases; "
            "use the hosted database backups for PostgreSQL."
        )
    now = now_dt or utc_now()
    now_ist = to_ist(now)
    timestamp_str = now_ist.strftime("%Y%m%d-%H%M%S")

    dest_dir = backup_dir or settings.backup_path
    dest_dir.mkdir(parents=True, exist_ok=True)
    target_path = dest_dir / f"shop-{timestamp_str}.db"

    source = src_path or get_sqlite_source_path()
    if not source.exists():
        logger.warning("Database source file %s does not exist yet; skipping backup", source)
        return target_path

    # Perform online backup
    src_conn = sqlite3.connect(str(source))
    dest_conn = sqlite3.connect(str(target_path))
    try:
        with dest_conn:
            src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    # Verify backup integrity
    chk_conn = sqlite3.connect(str(target_path))
    try:
        res = chk_conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0] != "ok":
            target_path.unlink(missing_ok=True)
            raise RuntimeError(f"Backup failed integrity check: {res}")
    finally:
        chk_conn.close()

    prune_backups(keep=30, backup_dir=dest_dir)
    logger.info("Created backup successfully: %s", target_path)
    return target_path


def restore_backup_file(backup_path: Path, target_db_path: Path | None = None) -> None:
    """Safely restore a backup file into the target database path in WAL mode.

    Removes -wal and -shm files before restoring to avoid WAL corruption.
    """
    import shutil

    b_path = Path(backup_path)
    target = Path(target_db_path) if target_db_path else get_sqlite_source_path()

    if not b_path.exists():
        raise FileNotFoundError(f"Backup file not found: {b_path}")

    # 1. Verify backup integrity
    conn = sqlite3.connect(str(b_path))
    try:
        res = conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0] != "ok":
            raise RuntimeError(f"Backup file failed integrity check: {res}")
    finally:
        conn.close()

    # 2. Dispose engine
    try:
        from app.db import engine

        engine.dispose()
    except Exception as e:
        logger.warning("Engine disposal note during restore: %s", e)

    # 3. Clean up wal and shm files
    target_str = str(target)
    Path(f"{target_str}-wal").unlink(missing_ok=True)
    Path(f"{target_str}-shm").unlink(missing_ok=True)

    # 4. Copy backup to target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(b_path, target)

    # Verify target integrity
    tgt_conn = sqlite3.connect(str(target))
    try:
        res = tgt_conn.execute("PRAGMA integrity_check;").fetchone()
        if not res or res[0] != "ok":
            raise RuntimeError(f"Restored database failed integrity check: {res}")
    finally:
        tgt_conn.close()

    logger.info("Restored database from %s to %s successfully", b_path, target)




def prune_backups(keep: int = 30, backup_dir: Path | None = None) -> list[Path]:
    dest_dir = backup_dir or settings.backup_path
    backups = sorted(dest_dir.glob("shop-*.db"), key=os.path.getmtime, reverse=True)
    pruned = []
    if len(backups) > keep:
        for b in backups[keep:]:
            try:
                b.unlink()
                pruned.append(b)
            except Exception as e:
                logger.error("Failed to prune backup %s: %e", b, e)
    return pruned


def list_backups() -> list[dict]:
    if not settings.uses_sqlite or settings.is_vercel:
        return []
    backup_dir = settings.backup_path
    backups = sorted(backup_dir.glob("shop-*.db"), key=os.path.getmtime, reverse=True)
    result = []
    for b in backups:
        stat = b.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        result.append({
            "filename": b.name,
            "path": str(b),
            "size_bytes": stat.st_size,
            "mtime": mtime,
            "formatted_time": to_ist(mtime).strftime("%d-%b-%Y %I:%M %p"),
        })
    return result


def run_startup_catchup_backup() -> bool:
    """Run catch-up backup if the newest backup is older than 24 hours."""
    backups = list_backups()
    now = utc_now()
    if not backups:
        create_backup(now)
        return True

    newest_mtime = backups[0]["mtime"]
    if (now - newest_mtime) > timedelta(hours=24):
        logger.info("Newest backup older than 24 hours; running startup catch-up backup")
        create_backup(now)
        return True
    return False


def start_backup_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=IST)
    # 02:00 IST nightly
    scheduler.add_job(
        create_backup,
        trigger=CronTrigger(hour=2, minute=0, timezone=IST),
        id="nightly_backup",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
