"""
T94 — Migration: tambah kolom staging ke kuitansi + CREATE TABLE wa_sessions.

Idempotent — aman jalan berulang. SQLite syntax dipakai untuk dev. Untuk
PostgreSQL production, jalankan ulang (CREATE TABLE IF NOT EXISTS sudah
aman, ALTER TABLE ADD COLUMN akan error kalau kolom sudah ada — di-handle
try/except per kolom).

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/migrate_wa_staging.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import text, inspect
from app.core.database import engine, Base, SessionLocal
# Import ALL models agar Base.metadata.create_all() bisa create wa_sessions
from app.models.wa_session import WaSession  # noqa: F401


def add_column_if_missing(conn, table_name: str, column_name: str, column_def: str):
    """Tambah kolom ke tabel kalau belum ada (SQLite-compatible)."""
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        print(f"  · Tabel {table_name} belum ada, skip")
        return
    existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name in existing_cols:
        print(f"  · Kolom {table_name}.{column_name} sudah ada, skip")
        return
    try:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
        print(f"  ✓ Tambah kolom: {table_name}.{column_name}")
    except Exception as e:
        print(f"  ! Gagal tambah {table_name}.{column_name}: {e}")


def create_index_if_missing(conn, table_name: str, index_name: str, columns: list[str]):
    """Buat index kalau belum ada."""
    inspector = inspect(conn)
    existing_indexes = {i["name"] for i in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        print(f"  · Index {index_name} sudah ada, skip")
        return
    cols_sql = ", ".join(columns)
    try:
        conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({cols_sql})"))
        print(f"  ✓ Buat index: {index_name} ON {table_name}({cols_sql})")
    except Exception as e:
        print(f"  ! Gagal buat index {index_name}: {e}")


def main():
    print("=" * 60)
    print("T94 Migration: WA Input Bot staging columns + wa_sessions")
    print("=" * 60)

    # 1) Create wa_sessions table (kalau belum ada)
    print("\n→ CREATE TABLE wa_sessions:")
    Base.metadata.create_all(bind=engine, tables=[WaSession.__table__])

    # Verify
    inspector = inspect(engine)
    if "wa_sessions" in inspector.get_table_names():
        print("  ✓ Tabel wa_sessions ada")
    else:
        print("  ✗ Tabel wa_sessions gagal dibuat")
        return

    # 2) ALTER TABLE kuitansi — tambah kolom staging
    print("\n→ ALTER TABLE kuitansi (add staging columns):")
    with engine.begin() as conn:
        add_column_if_missing(conn, "kuitansi", "staging_id", "INTEGER")
        add_column_if_missing(conn, "kuitansi", "is_finalized", "BOOLEAN DEFAULT 1 NOT NULL")
        add_column_if_missing(conn, "kuitansi", "finalized_at", "DATETIME")
        add_column_if_missing(conn, "kuitansi", "created_via", "VARCHAR(16) DEFAULT 'web' NOT NULL")
        add_column_if_missing(conn, "kuitansi", "wa_message_id", "VARCHAR(64)")
        add_column_if_missing(conn, "kuitansi", "wa_sender", "VARCHAR(32)")
        add_column_if_missing(conn, "kuitansi", "sabat_sesi", "VARCHAR(16)")
        add_column_if_missing(conn, "kuitansi", "temp_nomor", "VARCHAR(32)")

    # 3) Tambah index untuk query pattern umum
    print("\n→ CREATE INDEX:")
    with engine.begin() as conn:
        create_index_if_missing(conn, "kuitansi", "ix_kuitansi_tenant_finalized", ["tenant_id", "is_finalized"])
        create_index_if_missing(conn, "kuitansi", "ix_kuitansi_staging", ["staging_id"])
        create_index_if_missing(conn, "kuitansi", "ix_kuitansi_created_via", ["created_via"])
        create_index_if_missing(conn, "kuitansi", "ix_kuitansi_sabat_sesi", ["sabat_sesi"])

    # 4) Backfill: existing rows dianggap finalized
    print("\n→ Backfill existing rows:")
    with engine.begin() as conn:
        result = conn.execute(text("UPDATE kuitansi SET is_finalized=1 WHERE is_finalized IS NULL"))
        print(f"  ✓ {result.rowcount} rows backfilled is_finalized=1")

        result = conn.execute(text("UPDATE kuitansi SET created_via='web' WHERE created_via IS NULL"))
        print(f"  ✓ {result.rowcount} rows backfilled created_via='web'")

    print("\n" + "=" * 60)
    print("✓ Migration selesai")
    print("=" * 60)


if __name__ == "__main__":
    main()