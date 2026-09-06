"""
FASE 3-S2.T3 — Re-encrypt PII columns with NEW Fernet key.

PRASYARAT (jalankan urutan ini):
  1. Generate NEW key:
        python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. Update .env:
        PII_ENCRYPTION_KEY=<NEW>            # current production key
        PII_ENCRYPTION_KEY_PREVIOUS=<OLD>   # OLD key, untuk decrypt ciphertext lama
  3. Restart app (decrypt_pii sekarang pakai dual-key fallback).
  4. JALANKAN SCRIPT INI untuk re-encrypt semua ciphertext lama dengan key baru:
        /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/rotate_pii_to_new_key.py
  5. Konfirmasi ZERO error. Kalau clean, kosongkan PII_ENCRYPTION_KEY_PREVIOUS di .env
     dan restart app. Sekarang hanya primary yang aktif.

Idempotent. Aman jalan berulang (ciphertext yang sudah pakai primary akan
match dengan decrypt+encrypt dan tidak berubah isi).

Cara kerja:
  - Baca semua row yang punya kolom PII non-null.
  - Untuk tiap ciphertext: decrypt_pii() → kalau berhasil, encrypt_pii() ulang
    dengan key baru. Update row kalau ciphertext berubah.
  - Decrypt menggunakan dual-key fallback, jadi OLD ciphertext aman di-decrypt.
  - Cek: setelah re-encrypt, decrypt lagi HARUS menghasilkan plaintext yang sama.

Kolom PII yang di-rotasi (saat ini):
  - users.nomor_whatsapp_encrypted
  - users.totp_secret_encrypted
  - kuitansi.nama_umat_encrypted
  - kuitansi.nomor_whatsapp_encrypted
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import decrypt_pii, encrypt_pii  # noqa: E402

# (table_name, column_name) — semua kolom PII yang perlu di-re-encrypt
PII_COLUMNS = [
    ("users", "nomor_whatsapp_encrypted"),
    ("users", "totp_secret_encrypted"),
    ("kuitansi", "nama_umat_encrypted"),
    ("kuitansi", "nomor_whatsapp_encrypted"),
]


def rotate_table(db, table: str, column: str) -> dict:
    """Re-encrypt semua row pada kolom tertentu.

    Returns dict {total, decrypted, re_encrypted, skipped_empty, failed}.
    """
    stats = {"total": 0, "decrypted": 0, "re_encrypted": 0, "skipped_empty": 0, "failed": 0}

    print(f"\n[{table}.{column}] scanning ...")
    rows = db.execute(text(
        f"SELECT id, {column} FROM {table} "
        f"WHERE {column} IS NOT NULL AND {column} != ''"
    )).fetchall()

    stats["total"] = len(rows)
    print(f"  · {len(rows)} row(s) dengan ciphertext non-null")

    for row in rows:
        row_id = row[0]
        old_token = row[1]
        if not old_token:
            stats["skipped_empty"] += 1
            continue
        try:
            # 1. Decrypt (mungkin via primary atau previous-key fallback)
            plaintext = decrypt_pii(old_token)
            if not plaintext:
                stats["failed"] += 1
                print(f"  ! Row {row_id}: decrypt gagal (empty result). Skip.")
                continue
            stats["decrypted"] += 1

            # 2. Re-encrypt dengan primary key (NEW)
            new_token = encrypt_pii(plaintext)

            # 3. Cek round-trip: decrypt lagi harus sama
            verify = decrypt_pii(new_token)
            if verify != plaintext:
                stats["failed"] += 1
                print(f"  ! Row {row_id}: round-trip verify GAGAL. Skip update.")
                continue

            # 4. Update hanya kalau token berubah
            if new_token != old_token:
                db.execute(text(
                    f"UPDATE {table} SET {column} = :new WHERE id = :id"
                ), {"new": new_token, "id": row_id})
                stats["re_encrypted"] += 1
        except Exception as e:
            stats["failed"] += 1
            print(f"  ! Row {row_id}: exception {e!r}. Skip.")

    db.commit()
    return stats


def main():
    print("=" * 60)
    print("FASE 3-S2.T3 — PII Fernet re-encryption tool")
    print("=" * 60)
    print()

    # Sanity check: kalau PII_ENCRYPTION_KEY_PREVIOUS kosong, jangan izinkan run
    # supaya admin sadar mereka menjalankan tanpa fallback window.
    from app.core.config import settings
    if not settings.PII_ENCRYPTION_KEY_PREVIOUS:
        print("PERINGATAN: PII_ENCRYPTION_KEY_PREVIOUS tidak di-set di .env.")
        print("Script ini berguna setelah admin set dual-key window untuk rotasi.")
        print("Kalau hanya ingin re-encrypt data yang sudah pakai current key,")
        print("jalankan saja — script idempotent dan tidak akan mengubah ciphertext")
        print("yang sudah benar.")
        print()

    db = SessionLocal()
    try:
        overall = {"total": 0, "decrypted": 0, "re_encrypted": 0, "skipped_empty": 0, "failed": 0}
        started = time.time()
        for table, column in PII_COLUMNS:
            stats = rotate_table(db, table, column)
            for k in overall:
                overall[k] += stats[k]
        elapsed = time.time() - started

        print()
        print("=" * 60)
        print(f"DONE in {elapsed:.2f}s")
        print(f"  Total rows scanned     : {overall['total']}")
        print(f"  Successfully decrypted : {overall['decrypted']}")
        print(f"  Re-encrypted with new  : {overall['re_encrypted']}")
        print(f"  Failed                 : {overall['failed']}")
        print("=" * 60)

        if overall["failed"] > 0:
            print("\nADA FAILURE — investigate dulu sebelum kosongkan PII_ENCRYPTION_KEY_PREVIOUS.")
            sys.exit(1)
        elif overall["re_encrypted"] == 0:
            print("\nTidak ada ciphertext yang perlu di-re-encrypt (semua sudah pakai primary key).")
        else:
            print(f"\n{overall['re_encrypted']} ciphertext berhasil di-re-encrypt.")
            print("LANGKAH SELANJUTNYA:")
            print("  1. Verify app berjalan normal (decrypt_pii masih jalan via fallback).")
            print("  2. Kosongkan PII_ENCRYPTION_KEY_PREVIOUS di .env.")
            print("  3. Restart app.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
