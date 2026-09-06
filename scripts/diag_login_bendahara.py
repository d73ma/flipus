"""
T111 diagnostic (2026-08-26): Cek user bendahara_a ada atau tidak di DB.
Jerry lapor 'Not Found' saat login.

Usage:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 scripts/diag_login_bendahara.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def main():
    db = SessionLocal()
    try:
        # 1) Cari semua user role BENDAHARA
        rows = db.query(User).filter(User.role == "BENDAHARA").all()
        print(f"Total user role BENDAHARA: {len(rows)}")
        for u in rows:
            print(f"  id={u.id} username={u.username!r} tenant_id={u.tenant_id} active={u.is_active}")

        # 2) Cek username 'bendahara_a' specifically
        u = db.query(User).filter(User.username == "bendahara_a").first()
        if u:
            print(f"\n✅ Found bendahara_a: id={u.id} tenant_id={u.tenant_id} active={u.is_active} hashed_pw_len={len(u.password_hash or '')}")
        else:
            print("\n❌ Username 'bendahara_a' TIDAK ADA di DB")

        # 3) Tampilkan semua username
        all_users = db.query(User).all()
        print(f"\nSemua username di DB ({len(all_users)} total):")
        for u in all_users[:20]:
            print(f"  {u.username!r} role={u.role} tenant_id={u.tenant_id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
