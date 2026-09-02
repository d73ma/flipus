"""FLIPUS Retention Daemon. Purge kuitansi >N bulan."""
import os
import sys
import argparse
import hashlib
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.getcwd())
from app.core.database import SessionLocal, Base, engine
from app.models.transaction import Kuitansi
from app.models.audit import AuditLog
Base.metadata.create_all(bind=engine)
def run_retention(months=30, dry=False):
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=months * 30)
        print(f"[RETENTION] cutoff: {cutoff.isoformat()}")
        print(f"[RETENTION] retention: {months} bulan | dry-run: {dry}")
        cands = db.query(Kuitansi).filter(Kuitansi.created_at < cutoff).filter(Kuitansi.is_purged == False).all()
        print(f"[RETENTION] kandidat: {len(cands)}")
        purged_records = []  # list of {id, tenant_id} for audit logging
        for k in cands:
            age = round((now - k.created_at).days / 30, 1) if k.created_at else 0
            print(f"  - id={k.id} nomor={k.nomor_kuitansi} umur={age} bln")
            if not dry:
                k.is_purged = True
                k.nama_umat_encrypted = ""
                k.nomor_whatsapp_encrypted = ""
                purged_records.append({"id": k.id, "tenant_id": k.tenant_id})
        if not dry and purged_records:
            # Audit per kuitansi (per-tenant), schema-compatible (T93, 2026-08-23)
            for rec in purged_records:
                audit = AuditLog(
                    tenant_id=rec["tenant_id"],
                    action="PURGED",
                    payload_hash=hashlib.sha256(f"retention:{rec['id']}".encode()).hexdigest()[:32],
                )
                db.add(audit)
            db.commit()
            print(f"[RETENTION] purged={len(purged_records)} (audit logged)")
        elif dry:
            print("[RETENTION] DRY-RUN: no changes")
        return {"cutoff": cutoff.isoformat(), "months": months, "candidates": len(cands), "purged": 0 if dry else len(purged_records), "dry": dry}
    finally:
        db.close()
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--months", type=int, default=30)
    a = p.parse_args()
    s = run_retention(months=a.months, dry=a.dry_run)
    print("SUMMARY:", s)
if __name__ == "__main__":
    main()