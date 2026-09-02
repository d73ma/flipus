"""
v1.5-A/D — Migration: tambah tabel revoked_tokens + kolom password_changed_at ke users.

Idempotent. Aman jalan berulang.

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/migrate_v15_auth.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import text, inspect
from app.core.database import engine, Base, SessionLocal
# Import ALL models agar Base.metadata.create_all() bisa create revoked_tokens
from app.models.revoked_token import RevokedToken  # noqa: F401


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


def main():
    print("=" * 60)
    print("v1.5-A/D Migration: revoked_tokens + password_changed_at")
    print("=" * 60)

    # 1) CREATE TABLE revoked_tokens (idempotent via create_all)
    print("\n→ CREATE TABLE revoked_tokens:")
    Base.metadata.create_all(bind=engine, tables=[RevokedToken.__table__])
    inspector = inspect(engine)
    if "revoked_tokens" in inspector.get_table_names():
        print("  ✓ Tabel revoked_tokens ada")
    else:
        print("  ✗ Tabel revoked_tokens gagal dibuat")
        return

    # 2) ALTER TABLE users ADD COLUMN password_changed_at
    print("\n→ ALTER TABLE users (add password_changed_at):")
    with engine.begin() as conn:
        add_column_if_missing(conn, "users", "password_changed_at", "DATETIME")

    print("\n" + "=" * 60)
    print("✓ v1.5-A/D Migration selesai")
    print("=" * 60)


if __name__ == "__main__":
    main()