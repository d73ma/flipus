"""Re-hash password semua user agar kompatibel dengan library sekarang."""
import os
import sys
sys.path.insert(0, os.getcwd())
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password, verify_password

USERS = [
    ("admin_uni", "AdminUni123!"),
    ("auditor_misi", "AuditMisi123!"),
    ("pendeta", "Pendeta123!"),
    ("ketua_keuang", "Ketua123!"),
    ("bendahara", "Bendahara123!"),
]

db = SessionLocal()
for username, pwd in USERS:
    u = db.query(User).filter(User.username == username).first()
    if not u:
        print("  SKIP (tidak ada):", username)
        continue
    old_hash = u.password_hash
    new_hash = hash_password(pwd)
    u.password_hash = new_hash
    ok = verify_password(pwd, new_hash)
    print("  ~", username, "| verify baru:", ok)
db.commit()
db.close()
print("DONE")