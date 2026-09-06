"""
FLIPUS v1.1 — Backup & Restore service.

Untuk SQLite (jemaat lokal):
- Backup: copy file .db ke storage/backups/flipus-{timestamp}.db (binary safe)
          + opsional generate SQL dump (.sql) untuk portability
- Restore: copy file backup ke lokasi DB asli, ATAI jalankan SQL dump

Safety:
- Selalu backup lagi sebelum restore (auto-backup sebelum destroy)
- Validasi file exists + readable
- Return path & size untuk verifikasi

Storage location: storage/backups/
Retention: keep 7 backup terakhir (auto-cleanup)
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core.config import settings

# Path constants
BACKUP_DIR_NAME = "backups"
SQLITE_MAGIC = b"SQLite format 3\x00"


def _get_db_path() -> Path:
    """Extract path from SQLite URL 'sqlite:///./flipus_local.db'."""
    url = settings.DATABASE_URL_LOCAL
    # Remove prefix
    if url.startswith("sqlite:///"):
        path_str = url[10:]
    elif url.startswith("sqlite://"):
        path_str = url[9:]
    else:
        raise ValueError(f"Unsupported DB URL: {url}")

    # Relative path → join with cwd
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _ensure_backup_dir() -> Path:
    """Create storage/backups/ kalau belum ada."""
    backup_dir = Path.cwd() / "storage" / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_database(retention: int = 7) -> dict:
    """
    Backup SQLite DB ke storage/backups/.

    Args:
        retention: berapa backup terakhir yang disimpan (default 7)

    Returns:
        dict {status, path, filename, size_bytes, created_at}
    """
    db_path = _get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    backup_dir = _ensure_backup_dir()
    ts = _timestamp()
    filename = f"flipus_backup_{ts}.db"
    dest = backup_dir / filename

    # 1) Copy binary (.db) - cepat, integrity preserved
    shutil.copy2(str(db_path), str(dest))

    size = dest.stat().st_size

    # 2) Cleanup old backups beyond retention
    deleted = _cleanup_old_backups(retention=retention)

    return {
        "status": "ok",
        "path": str(dest),
        "filename": filename,
        "size_bytes": size,
        "created_at": datetime.now().isoformat(),
        "old_backups_deleted": deleted,
        "method": "binary_copy",
    }


def backup_database_sql(retention: int = 7) -> dict:
    """
    Backup DB sebagai SQL dump (text).

    Slower tapi portable — bisa di-restore ke DB SQLite lain atau PostgreSQL
    (dengan penyesuaian).
    """
    db_path = _get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    backup_dir = _ensure_backup_dir()
    ts = _timestamp()
    filename = f"flipus_dump_{ts}.sql"
    dest = backup_dir / filename

    conn = sqlite3.connect(str(db_path))
    try:
        with open(dest, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()

    size = dest.stat().st_size
    deleted = _cleanup_old_backups(retention=retention, pattern="flipus_dump_")

    return {
        "status": "ok",
        "path": str(dest),
        "filename": filename,
        "size_bytes": size,
        "created_at": datetime.now().isoformat(),
        "old_backups_deleted": deleted,
        "method": "sql_dump",
    }


def _cleanup_old_backups(retention: int, pattern: str = "flipus_backup_") -> list[str]:
    """Hapus backup lama, simpan N terakhir."""
    backup_dir = Path.cwd() / "storage" / BACKUP_DIR_NAME
    if not backup_dir.exists():
        return []
    files = sorted(
        backup_dir.glob(f"{pattern}*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted = []
    for f in files[retention:]:
        f.unlink()
        deleted.append(f.name)
    return deleted


def list_backups() -> list[dict]:
    """List semua backup files di storage/backups/."""
    backup_dir = _ensure_backup_dir()
    items = []
    for f in sorted(backup_dir.glob("flipus_*"), key=lambda p: p.stat().st_mtime, reverse=True):
        items.append({
            "filename": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "kind": "sql_dump" if "_dump_" in f.name else "binary",
        })
    return items


def restore_database(filename: str, auto_backup_before: bool = True) -> dict:
    """
    Restore DB dari backup file.

    Safety:
    - Kalau auto_backup_before, backup DB dulu sebelum overwrite
    - Validasi file exists + format (SQLite magic bytes)

    Args:
        filename: nama file di storage/backups/
        auto_backup_before: backup otomatis sebelum restore (default True)

    Returns:
        dict {status, restored_from, auto_backup_path (kalau ada)}
    """
    backup_dir = _ensure_backup_dir()
    src = backup_dir / filename
    if not src.exists():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    db_path = _get_db_path()

    # Auto-backup sebelum restore
    auto_backup_path = None
    if auto_backup_before:
        try:
            auto = backup_database(retention=99)  # don't cleanup
            auto_backup_path = auto["path"]
        except Exception as e:
            raise RuntimeError(f'Auto-backup sebelum restore gagal: {e}') from e

    # Validate SQLite magic (kalau .db file)
    if src.suffix == ".db":
        with open(src, "rb") as f:
            magic = f.read(len(SQLITE_MAGIC))
        if magic != SQLITE_MAGIC:
            raise ValueError(f"File bukan SQLite DB valid: {filename}")

        # Overwrite DB
        shutil.copy2(str(src), str(db_path))
        method = "binary_restore"
    elif src.suffix == ".sql":
        # Run SQL dump
        conn = sqlite3.connect(str(db_path))
        try:
            with open(src, "r", encoding="utf-8") as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.commit()
        finally:
            conn.close()
        method = "sql_restore"
    else:
        raise ValueError(f"Format file tidak dikenal: {src.suffix}")

    return {
        "status": "restored",
        "restored_from": str(src),
        "filename": filename,
        "auto_backup_path": auto_backup_path,
        "restored_at": datetime.now().isoformat(),
        "method": method,
    }
