"""
Rollback Bendahara ke nomor dummy (selain bendahara_a).

Kasus: update_bendahara_wa.py default update SEMUA Bendahara ke nomor Jerry,
mengakibatkan multi-tenant match. Script ini rollback ke dummy numbers supaya
hanya bendahara_a (Nataan demo) yang match Jerry's real number.

Default dummy numbers per Bendahara (dari seed):
- bendahara_a (Nataan): 628124809145 (Jerry, keep)
- bendahara lainnya: 628123450001, 628123450002, ... (dummy placeholder)

Run:
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/rollback_bendahara_wa.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import encrypt_pii  # noqa: E402
from app.models.user import User  # noqa: E402

# Username → dummy number (avoid real numbers — pakai range 6281234500xx khusus dummy)
DUMMY_NUMBERS = {
    "bendahara_a": "628124809145",  # Jerry's real number (keep)
    # Sisanya di-set ke dummy 62812345xxxx yang jelas-jelas dummy
}


def main():
    db = SessionLocal()
    try:
        bendaharas = db.query(User).filter(User.role == "BENDAHARA").order_by(User.id).all()
        if not bendaharas:
            print("  ! Tidak ada Bendahara")
            return

        print(f"Ditemukan {len(bendaharas)} Bendahara:")
        for idx, b in enumerate(bendaharas):
            old = b.nomor_whatsapp or "(kosong)"
            # Set dummy kecuali bendahara_a (idx 0)
            if b.username == "bendahara_a":
                target = "628124809145"  # Jerry's number, keep
                keep = True
            else:
                target = f"6281234500{idx:02d}"  # dummy
                keep = False

            b.nomor_whatsapp = target
            b.nomor_whatsapp_encrypted = encrypt_pii(target)
            db.add(b)
            mark = "→ (KEEP Jerry)" if keep else "→ (dummy)"
            print(f"  · {b.username:20s} WA lama={old} {mark} WA baru={target}")

        db.commit()
        print(f"\n✓ {len(bendaharas)} Bendahara di-rollback. Hanya bendahara_a (Nataan) yang match Jerry.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
