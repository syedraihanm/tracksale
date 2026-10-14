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


def test_wal_safe_restore():
    from app.services.backup import restore_backup_file

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "live.db"
        backup_dir = temp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # 1. Initialize SQLite database in WAL mode
        conn1 = sqlite3.connect(str(db_path))
        try:
            conn1.execute("PRAGMA journal_mode=WAL;")
            conn1.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, val TEXT);")
            conn1.execute("INSERT INTO test_data (val) VALUES ('initial_state');")
            conn1.commit()
        finally:
            conn1.close()

        # 2. Create online backup of initial state
        backup_file = create_backup(src_path=db_path, backup_dir=backup_dir)
        assert backup_file.exists()

        # 3. Mutate live database with new data so WAL frames exist
        conn2 = sqlite3.connect(str(db_path))
        try:
            conn2.execute("INSERT INTO test_data (val) VALUES ('mutated_state');")
            conn2.commit()
        finally:
            conn2.close()

        # Create dummy sidecar files to test removal
        wal_file = Path(f"{db_path}-wal")
        shm_file = Path(f"{db_path}-shm")
        wal_file.touch(exist_ok=True)
        shm_file.touch(exist_ok=True)
        assert wal_file.exists()

        # 4. Invoke restore_backup_file
        restore_backup_file(backup_path=backup_file, target_db_path=db_path)

        # Assert wal and shm files were safely cleaned up
        assert not wal_file.exists()
        assert not shm_file.exists()

        # Verify integrity and content of restored database
        conn3 = sqlite3.connect(str(db_path))
        try:
            res = conn3.execute("PRAGMA integrity_check;").fetchone()
            assert res[0] == "ok"

            rows = conn3.execute("SELECT val FROM test_data;").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "initial_state"
        finally:
            conn3.close()


