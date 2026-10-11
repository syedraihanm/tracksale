import sqlite3
import tempfile
from pathlib import Path

from app.services.backup import create_backup, prune_backups


def test_backup_and_integrity_check(temp_db):
    """AC9: SQLite online backup produces non-corrupt database passing PRAGMA integrity_check."""
    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir = Path(temp_dir) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Get DB path from session
        db_path = Path(temp_db.get_bind().url.database)

        # Run backup
        backup_file = create_backup(src_path=db_path, backup_dir=backup_dir)
        assert backup_file.exists()
        assert backup_file.suffix == ".db"
        assert backup_file.stat().st_size > 0

        # Run PRAGMA integrity_check on the backup
        conn = sqlite3.connect(backup_file)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        row = cursor.fetchone()
        assert row[0] == "ok"
        conn.close()


def test_backup_pruning():
    """Verify retention policy keeps the latest 30 backups and prunes older ones."""
    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir = Path(temp_dir) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create 35 dummy backup files with staggered timestamps
        for i in range(35):
            f = backup_dir / f"shop-20261010-1200{i:02d}.db"
            f.write_text("test")

        backups_before = list(backup_dir.glob("shop-*.db"))
        assert len(backups_before) == 35

        deleted = prune_backups(keep=30, backup_dir=backup_dir)
        assert len(deleted) == 5

        backups_after = list(backup_dir.glob("shop-*.db"))
        assert len(backups_after) == 30
