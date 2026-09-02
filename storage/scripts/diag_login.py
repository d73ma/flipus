"""Diagnostik login gagal."""
import os
import sys
sys.path.insert(0, os.getcwd())
from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import verify_password

db = SessionLocal()
u = db.query(User).filter(User.username == "bendahara").first()
if not u:
    print("USER TIDAK ADA! List semua user:")
    for x in db.query(User).all():
        print("  username:", x.username, "| role:", x.role, "| tenant_id:", x.tenant_id)
else:
    print("USER ADA:", u.username, "| role:", u.role, "| active:", u.is_active)
    print("Hash prefix:", u.password_hash[:30], "...")
    print("Test verify_password Bendahara123!:", verify_password("Bendahara123!", u.password_hash))
    print("Test verify_password salah:", verify_password("salahpassword", u.password_hash))
db.close()