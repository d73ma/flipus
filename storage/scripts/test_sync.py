"""Test sync upload + pull end-to-end."""
import os
import sys
import requests
sys.path.insert(0, os.getcwd())
from app.core.security import create_access_token
from app.core.database import SessionLocal
from app.models.user import User

BASE = "http://localhost:8000/api/v1"
db = SessionLocal()
b = db.query(User).filter(User.username == "bendahara").first()
a = db.query(User).filter(User.username == "auditor_misi").first()
u = db.query(User).filter(User.username == "admin_uni").first()
db.close()
bt = create_access_token({"sub": str(b.id)})
at = create_access_token({"sub": str(a.id)})
ut = create_access_token({"sub": str(u.id)})
print("=== UPLOAD (bendahara) ===")
r = requests.post(BASE + "/sync/upload", headers={"Authorization": "Bearer " + bt}, timeout=30)
print("status:", r.status_code)
print("body:", r.json())
print("=== PULL (auditor) ===")
r = requests.get(BASE + "/sync/pull", headers={"Authorization": "Bearer " + at}, timeout=30)
print("status:", r.status_code)
print("count:", r.json().get("count"))
print("=== PULL (admin_uni) ===")
r = requests.get(BASE + "/sync/pull", headers={"Authorization": "Bearer " + ut}, timeout=30)
print("status:", r.status_code)
print("count:", r.json().get("count"))
print("=== PULL forbidden (bendahara coba pull) ===")
r = requests.get(BASE + "/sync/pull", headers={"Authorization": "Bearer " + bt}, timeout=30)
print("status:", r.status_code, "(expected 403)")