"""Test anonymizer strip PII."""
import os
import sys
sys.path.insert(0, os.getcwd())
from app.core.database import SessionLocal
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.services.anonymizer import anonymize_kuitansi, verify_hash
db = SessionLocal()
k = db.query(Kuitansi).filter(Kuitansi.id == 2).first()
t = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
print("TENANT:", t.nama_jemaat_lokal)
print("---")
print("RAW (PII yang ada di DB jemaat):")
print("  nama_umat_encrypted =", (k.nama_umat_encrypted[:30] if k.nama_umat_encrypted else None))
print("  nomor_whatsapp_encrypted =", (k.nomor_whatsapp_encrypted[:30] if k.nomor_whatsapp_encrypted else None))
print("  foto_amplop_path =", k.foto_amplop_path)
print("---")
safe = anonymize_kuitansi(k, t.nama_jemaat_lokal)
print("SAFE (siap sync ke Kantor Misi):")
for key, val in safe.items():
    print("  {}: {}".format(key, val))
print("---")
print("HASH VERIFY:", verify_hash(safe))
db.close()