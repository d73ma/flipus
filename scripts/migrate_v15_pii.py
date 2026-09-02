"""
v1.5-E — Migration: tambah kolom users.nomor_whatsapp_encrypted (Fernet).

Idempotent. Aman jalan berulang.

Backfill: untuk setiap user yang punya nomor_whatsapp plain tapi belum punya
encrypted, encrypt dan simpan. Aman jalan ulang — skip yang sudah ada.

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/migrate_v15_pii.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import text, inspect
from app.core.database import engine, SessionLocal
from app.core.security import encrypt_pii


def add_column_if_missing(conn, table_name: str, column_name: str, column_def: str):
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


def backfill_encrypted_numbers():
    """Backfill: encrypt users.nomor_whatsapp → users.nomor_whatsapp_encrypted."""
    db = SessionLocal()
    try:
        result = db.execute(text(
            "SELECT id, nomor_whatsapp FROM users "
            "WHERE nomor_whatsapp IS NOT NULL "
            "AND (nomor_whatsapp_encrypted IS NULL OR nomor_whatsapp_encrypted = '')"
        ))
        rows = result.fetchall()
        if not rows:
            print("  · Tidak ada row yang perlu di-backfill (semua sudah encrypted atau plain kosong)")
            return
        updated = 0
        for uid, plain_wa in rows:
            try:
                enc = encrypt_pii(plain_wa)
                db.execute(text(
                    "UPDATE users SET nomor_whatsapp_encrypted = :enc WHERE id = :uid"
                ), {"enc": enc, "uid": uid})
                updated += 1
            except Exception as e:
                print(f"  ! Gagal encrypt user id={uid}: {e}")
        db.commit()
        print(f"  ✓ Backfill: {updated} user rows ter-encrypt")
    finally:
        db.close()


def main():
    print("=" * 60)
    print("v1.5-E Migration: users.nomor_whatsapp_encrypted")
    print("=" * 60)

    print("\n→ ALTER TABLE users (add nomor_whatsapp_encrypted):")
    with engine.begin() as conn:
        add_column_if_missing(conn, "users", "nomor_whatsapp_encrypted", "VARCHAR(255)")

    print("\n→ Backfill encrypt nomor_whatsapp → nomor_whatsapp_encrypted:")
    backfill_encrypted_numbers()

    print("\n" + "=" * 60)
    print("✓ v1.5-E Migration selesai")
    print("=" * 60)


if __name__ == "__main__":
    main()