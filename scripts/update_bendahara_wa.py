"""
Update Bendahara demo ke nomor HP Jerry, untuk test WA Input Bot.

By default, set Bendahara 'bendahara_a' ke 628124809145 (Jerry's number).
Idempotent — bisa dijalankan ulang.

Run:
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/update_bendahara_wa.py
    # atau dengan nomor custom:
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/update_bendahara_wa.py 628123456789
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from app.core.database import SessionLocal
from app.core.security import encrypt_pii
from app.models.user import User


def main():
    # Jerry's number default (formatted to Fonnte standard 62xxx)
    wa_input = sys.argv[1] if len(sys.argv) > 1 else "628124809145"

    # Normalize: 08xx → 628xx
    wa_clean = wa_input.replace("+", "").replace(" ", "").replace("-", "")
    if wa_clean.startswith("0"):
        wa_clean = "62" + wa_clean[1:]
    elif not wa_clean.startswith("62") and wa_clean.isdigit():
        wa_clean = "62" + wa_clean

    print("=" * 60)
    print(f"Update Bendahara WA → {wa_clean}")
    print("=" * 60)

    db = SessionLocal()
    try:
        bendaharas = db.query(User).filter(User.role == "BENDAHARA").all()
        if not bendaharas:
            print("  ! Tidak ada user BENDAHARA di database")
            return

        print(f"\nDitemukan {len(bendaharas)} Bendahara:")
        for b in bendaharas:
            print(f"  · ID={b.id} username={b.username} nama={b.nama_lengkap} wa_lama={b.nomor_whatsapp}")

        # Update semua Bendahara (untuk test WA bot, semua jadi nomor Jerry)
        # Atau kalau mau update specific, pass username sebagai argv[2]
        target_username = sys.argv[2] if len(sys.argv) > 2 else None

        updated = 0
        for b in bendaharas:
            if target_username and b.username != target_username:
                continue
            b.nomor_whatsapp = wa_clean
            b.nomor_whatsapp_encrypted = encrypt_pii(wa_clean)
            db.add(b)
            updated += 1
            print(f"  ✓ Update {b.username} ({b.nama_lengkap}) → {wa_clean}")

        if updated == 0:
            print(f"\n  ! Tidak ada user dengan username '{target_username}' untuk di-update")
            return

        db.commit()
        print(f"\n✓ {updated} Bendahara ter-update ke {wa_clean}")
        print("\nSekarang bisa test:")
        print(f'  curl -X POST http://localhost:8000/api/v1/wa/inbound \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f'    -d \'{{"sender": "{wa_clean}", "message": "X 100rb, PT 50rb", "id": "test-jerry-1"}}\'')
    finally:
        db.close()


if __name__ == "__main__":
    main()