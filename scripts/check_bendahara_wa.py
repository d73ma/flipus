"""
Cek nomor WhatsApp Bendahara di database untuk test WA Input Bot.
Run: /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/check_bendahara_wa.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from app.core.database import SessionLocal  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402


def main():
    db = SessionLocal()
    try:
        bendaharas = db.query(User).filter(User.role == "BENDAHARA").all()
        print("=" * 70)
        print(f"BENDAHARA di database: {len(bendaharas)} user")
        print("=" * 70)
        print(f"{'ID':<5}{'Username':<22}{'Nama':<28}{'Tenant':<22}{'Nomor WA':<18}{'Active'}")
        print("-" * 110)
        for u in bendaharas:
            tenant = db.query(Tenant).filter(Tenant.id == u.tenant_id).first()
            nama_jemaat = tenant.nama_jemaat_lokal if tenant else "—"
            # Format WA: convert 08xx ke 628xx untuk Fonnte standard
            wa = u.nomor_whatsapp or "(kosong)"
            if wa.startswith("0"):
                wa_fonnte = "62" + wa[1:]
            else:
                wa_fonnte = wa
            print(f"{u.id:<5}{u.username:<22}{u.nama_lengkap:<28}{nama_jemaat:<22}{wa_fonnte:<18}{u.is_active}")
        print()
        print("Untuk test WA bot:")
        print("  curl -X POST http://localhost:8000/api/v1/wa/inbound \\")
        print("    -H 'Content-Type: application/json' \\")
        print("    -d '{\"sender\": \"<nomor_wa_fonnte>\", \"message\": \"X 100rb, PT 50rb\", \"id\": \"test\"}'")
    finally:
        db.close()


if __name__ == "__main__":
    main()
