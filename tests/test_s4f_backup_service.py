"""
S4-F.R4 — Unit tests untuk app.services.backup_service.

Coverage target: ~95% (102 stmts).

Functions covered:
- _get_db_path: parse DATABASE_URL_LOCAL → path (sqlite:///X, sqlite://X, error)
- _ensure_backup_dir: mkdir storage/backups/
- _timestamp: strftime format
- backup_database: binary copy .db → storage/backups/flipus_backup_{ts}.db
- backup_database_sql: text dump → storage/backups/flipus_dump_{ts}.sql
- _cleanup_old_backups: keep N terakhir, hapus sisanya
- list_backups: glob flipus_* + classify binary/sql_dump
- restore_database: validate magic bytes + restore .db / .sql

Strategy: pakai tmp_path pytest fixture + monkeypatch settings.DATABASE_URL_LOCAL
+ monkeypatch Path.cwd() agar tests tidak touch real storage/.
"""

import sqlite3
from pathlib import Path

import pytest


# Helper: build a small valid SQLite DB file with a `transaksi` table
def _make_sqlite_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE transaksi (id INTEGER PRIMARY KEY, nominal INTEGER)")
        conn.execute("INSERT INTO transaksi VALUES (1, 100000), (2, 250000)")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def fake_storage(tmp_path, monkeypatch):
    """Patch settings + Path.cwd() supaya backup pakai tmp_path."""
    db_file = tmp_path / "test_flipus.db"
    _make_sqlite_db(db_file)

    # Mock settings.DATABASE_URL_LOCAL → relative path "test_flipus.db"
    monkeypatch.setattr(
        "app.services.backup_service.settings.DATABASE_URL_LOCAL",
        f"sqlite:///{db_file.name}",
    )

    # Mock Path.cwd() → tmp_path (backup_dir = tmp_path/storage/backups)
    monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)

    return tmp_path, db_file


class TestGetDbPath:
    """Extract path dari DATABASE_URL_LOCAL."""

    def test_sqlite_relative_path(self, monkeypatch, tmp_path):
        """sqlite:///./flipus_local.db → relative path joined with cwd."""
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "sqlite:///./flipus_local.db",
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _get_db_path
        result = _get_db_path()
        assert result == tmp_path / "flipus_local.db"

    def test_sqlite_no_leading_slash(self, monkeypatch, tmp_path):
        """sqlite:///flipus.db → no leading ./"""
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "sqlite:///flipus.db",
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _get_db_path
        result = _get_db_path()
        assert result == tmp_path / "flipus.db"

    def test_sqlite_no_triple_slash(self, monkeypatch, tmp_path):
        """sqlite://flipus.db (relative) → joined with cwd."""
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "sqlite://flipus.db",
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _get_db_path
        result = _get_db_path()
        assert result == tmp_path / "flipus.db"

    def test_unsupported_url_raises(self, monkeypatch):
        """postgresql://... → ValueError."""
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "postgresql://localhost/db",
        )
        from app.services.backup_service import _get_db_path
        with pytest.raises(ValueError, match="Unsupported DB URL"):
            _get_db_path()


class TestEnsureBackupDir:
    """Create storage/backups/ kalau belum ada."""

    def test_creates_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _ensure_backup_dir
        result = _ensure_backup_dir()
        assert result == tmp_path / "storage" / "backups"
        assert result.exists()
        assert result.is_dir()

    def test_idempotent(self, monkeypatch, tmp_path):
        """Kalau sudah ada → no error."""
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _ensure_backup_dir
        _ensure_backup_dir()
        # Second call must not raise
        _ensure_backup_dir()
        assert (tmp_path / "storage" / "backups").exists()


class TestTimestamp:
    """_timestamp() returns YYYYMMDD_HHMMSS."""

    def test_format(self):
        from app.services.backup_service import _timestamp
        ts = _timestamp()
        # Format: "YYYYMMDD_HHMMSS" → 15 chars
        assert len(ts) == 15
        assert ts[8] == "_"
        # All digits except underscore
        assert all(c.isdigit() or c == "_" for c in ts)


class TestBackupDatabase:
    """Binary copy of DB to storage/backups/."""

    def test_success(self, fake_storage):
        tmp_path, db_file = fake_storage
        from app.services.backup_service import backup_database
        result = backup_database(retention=7)

        assert result["status"] == "ok"
        assert result["method"] == "binary_copy"
        assert result["filename"].startswith("flipus_backup_")
        assert result["filename"].endswith(".db")
        assert Path(result["path"]).exists()
        assert result["size_bytes"] > 0
        assert result["size_bytes"] == db_file.stat().st_size

    def test_creates_backup_file(self, fake_storage):
        tmp_path, db_file = fake_storage
        from app.services.backup_service import backup_database
        result = backup_database()
        backup_file = Path(result["path"])
        # File exists in tmp_path/storage/backups/
        assert backup_file.parent == tmp_path / "storage" / "backups"
        # First 16 bytes are SQLite magic
        with open(backup_file, "rb") as f:
            magic = f.read(16)
        assert magic == b"SQLite format 3\x00"

    def test_db_not_found_raises(self, monkeypatch, tmp_path):
        """DB path not exist → FileNotFoundError."""
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "sqlite:///nonexistent.db",
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import backup_database
        with pytest.raises(FileNotFoundError, match="DB not found"):
            backup_database()

    def test_retention_cleanup(self, fake_storage):
        """retention=2: hapus backup ke-3 dst."""
        tmp_path, _ = fake_storage
        from app.services.backup_service import backup_database, list_backups
        # Create 5 backups
        for _ in range(5):
            backup_database(retention=2)
            import time
            time.sleep(1.05)  # Ensure distinct mtime (filesystem granularity)

        backups = list_backups()
        binary_backups = [b for b in backups if b["kind"] == "binary"]
        # retention=2 → max 2 backups
        assert len(binary_backups) <= 2


class TestBackupDatabaseSql:
    """Text SQL dump."""

    def test_success(self, fake_storage):
        tmp_path, db_file = fake_storage
        from app.services.backup_service import backup_database_sql
        result = backup_database_sql(retention=7)

        assert result["status"] == "ok"
        assert result["method"] == "sql_dump"
        assert result["filename"].startswith("flipus_dump_")
        assert result["filename"].endswith(".sql")
        assert result["size_bytes"] > 0

        # SQL dump should contain CREATE TABLE + INSERT
        with open(result["path"], "r", encoding="utf-8") as f:
            content = f.read()
        assert "CREATE TABLE transaksi" in content
        assert "INSERT INTO" in content

    def test_db_not_found_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.services.backup_service.settings.DATABASE_URL_LOCAL",
            "sqlite:///nonexistent.db",
        )
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import backup_database_sql
        with pytest.raises(FileNotFoundError):
            backup_database_sql()

    def test_retention_cleanup_sql(self, fake_storage):
        """retention=1: hapus dump ke-2 dst."""
        tmp_path, _ = fake_storage
        from app.services.backup_service import backup_database_sql, list_backups
        for _ in range(3):
            backup_database_sql(retention=1)
            import time
            time.sleep(1.05)

        backups = list_backups()
        sql_dumps = [b for b in backups if b["kind"] == "sql_dump"]
        # retention=1 → max 1 dump
        assert len(sql_dumps) <= 1


class TestCleanupOldBackups:
    """Keep N terakhir, hapus sisanya."""

    def test_no_dir_returns_empty(self, monkeypatch, tmp_path):
        """Backup dir not exist → return []."""
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _cleanup_old_backups
        result = _cleanup_old_backups(retention=5)
        assert result == []

    def test_keeps_n_most_recent(self, monkeypatch, tmp_path):
        """Create 5 files, retention=2 → 2 newest remain."""
        backup_dir = tmp_path / "storage" / "backups"
        backup_dir.mkdir(parents=True)
        # Create 5 files with different mtimes
        files = []
        for i in range(5):
            f = backup_dir / f"flipus_backup_2026010{i}_120000.db"
            f.write_text(f"content-{i}")
            import time
            time.sleep(1.05)
            files.append(f)

        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import _cleanup_old_backups
        deleted = _cleanup_old_backups(retention=2, pattern="flipus_backup_")

        # 3 oldest deleted (file index 0, 1, 2)
        assert len(deleted) == 3
        # Only 2 newest remain
        remaining = sorted(backup_dir.glob("flipus_backup_*"))
        assert len(remaining) == 2


class TestListBackups:
    """List + classify backup files."""

    def test_empty_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import list_backups
        result = list_backups()
        assert result == []

    def test_classify_binary_and_sql(self, monkeypatch, tmp_path):
        backup_dir = tmp_path / "storage" / "backups"
        backup_dir.mkdir(parents=True)
        (backup_dir / "flipus_backup_20260101_120000.db").write_text("db1")
        (backup_dir / "flipus_dump_20260102_120000.sql").write_text("dump1")

        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import list_backups
        result = list_backups()

        assert len(result) == 2
        kinds = {item["kind"] for item in result}
        assert kinds == {"binary", "sql_dump"}

    def test_sorted_newest_first(self, monkeypatch, tmp_path):
        """list_backups diurutkan descending by mtime (newest first)."""
        backup_dir = tmp_path / "storage" / "backups"
        backup_dir.mkdir(parents=True)
        f1 = backup_dir / "flipus_backup_20260101_120000.db"
        f1.write_text("old")
        import time
        time.sleep(1.05)
        f2 = backup_dir / "flipus_backup_20260102_120000.db"
        f2.write_text("new")

        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)
        from app.services.backup_service import list_backups
        result = list_backups()

        assert result[0]["filename"] == "flipus_backup_20260102_120000.db"
        assert result[1]["filename"] == "flipus_backup_20260101_120000.db"


class TestRestoreDatabase:
    """Restore DB dari backup file."""

    def test_restore_binary(self, fake_storage):
        """Restore .db file → overwrite current DB."""
        tmp_path, db_file = fake_storage
        from app.services.backup_service import (
            backup_database,
            restore_database,
        )

        # Create backup
        backup_result = backup_database()
        backup_filename = backup_result["filename"]

        # Modify DB (simulate corruption/different state)
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        conn.execute("DELETE FROM transaksi WHERE id = 1")
        conn.commit()
        conn.close()

        # Restore
        result = restore_database(backup_filename, auto_backup_before=False)

        assert result["status"] == "restored"
        assert result["method"] == "binary_restore"
        assert result["restored_from"] == backup_result["path"]
        assert result["auto_backup_path"] is None

        # Verify data restored (row with id=1 is back)
        conn = sqlite3.connect(str(db_file))
        rows = conn.execute("SELECT COUNT(*) FROM transaksi").fetchone()
        assert rows[0] == 2

    def test_restore_invalid_magic_raises(self, fake_storage):
        """File bukan SQLite → ValueError."""
        tmp_path, _ = fake_storage
        backup_dir = tmp_path / "storage" / "backups"
        backup_dir.mkdir(exist_ok=True, parents=True)
        bogus = backup_dir / "flipus_backup_bogus.db"
        bogus.write_text("NOT A SQLITE FILE")

        from app.services.backup_service import restore_database
        with pytest.raises(ValueError, match="bukan SQLite DB valid"):
            restore_database("flipus_backup_bogus.db", auto_backup_before=False)

    def test_restore_unknown_suffix_raises(self, fake_storage):
        """Format .txt → ValueError."""
        tmp_path, _ = fake_storage
        backup_dir = tmp_path / "storage" / "backups"
        backup_dir.mkdir(exist_ok=True, parents=True)
        bogus = backup_dir / "flipus_bogus.txt"
        bogus.write_text("text")

        from app.services.backup_service import restore_database
        with pytest.raises(ValueError, match="Format file tidak dikenal"):
            restore_database("flipus_bogus.txt", auto_backup_before=False)

    def test_restore_missing_file_raises(self, fake_storage):
        """Backup file tidak ada → FileNotFoundError."""
        from app.services.backup_service import restore_database
        with pytest.raises(FileNotFoundError, match="Backup file not found"):
            restore_database("flipus_backup_nonexistent.db", auto_backup_before=False)

    def test_restore_sql_dump(self, fake_storage):
        """Restore .sql → run SQL script."""
        tmp_path, db_file = fake_storage
        from app.services.backup_service import (
            backup_database_sql,
            restore_database,
        )

        # Create SQL dump
        dump_result = backup_database_sql()
        dump_filename = dump_result["filename"]

        # Modify (drop table)
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        conn.execute("DROP TABLE transaksi")
        conn.commit()
        conn.close()

        # Restore from SQL dump
        result = restore_database(dump_filename, auto_backup_before=False)
        assert result["status"] == "restored"
        assert result["method"] == "sql_restore"

        # Verify table restored
        conn = sqlite3.connect(str(db_file))
        rows = conn.execute("SELECT COUNT(*) FROM transaksi").fetchone()
        assert rows[0] == 2

    def test_restore_with_auto_backup(self, fake_storage):
        """auto_backup_before=True (default) → backup dibuat dulu sebelum restore."""
        import time
        tmp_path, db_file = fake_storage
        from app.services.backup_service import (
            backup_database,
            restore_database,
        )

        # Create primary backup to restore
        primary_backup = backup_database()
        primary_filename = primary_backup["filename"]

        # Wait > 1s supaya auto-backup dapat timestamp berbeda
        time.sleep(1.1)

        # Restore with auto_backup (default True)
        result = restore_database(primary_filename)

        assert result["status"] == "restored"
        assert result["auto_backup_path"] is not None
        assert Path(result["auto_backup_path"]).exists()
        # Harus beda dari primary (timestamp berbeda)
        assert result["auto_backup_path"] != primary_backup["path"]
        # Auto backup filename beda (timestamp lebih baru)
        assert Path(result["auto_backup_path"]).name != primary_filename


class TestConstants:
    """Module-level constants."""

    def test_backup_dir_name(self):
        from app.services.backup_service import BACKUP_DIR_NAME
        assert BACKUP_DIR_NAME == "backups"

    def test_sqlite_magic(self):
        from app.services.backup_service import SQLITE_MAGIC
        assert SQLITE_MAGIC == b"SQLite format 3\x00"
        assert len(SQLITE_MAGIC) == 16
