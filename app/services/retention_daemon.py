"""
Retention Daemon — Hapus data PII di bulan ke-31.
Yang dipertahankan: ledger angka (jurnal umum).
Yang dihapus: nama, nomor WA, file foto amplop.
"""
import logging
import os
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.models.transaction import Kuitansi

logger = logging.getLogger(__name__)
STORAGE_AMPLOP_DIR = "storage/amplop_records"
RETENTION_MONTHS = 30

def run_retention_purge(db: Session) -> dict:
    cutoff = utcnow() - timedelta(days=30 * RETENTION_MONTHS)
    old_records = db.query(Kuitansi).filter(Kuitansi.created_at < cutoff).all()

    purged_count = 0
    files_removed = 0

    for rec in old_records:
        if rec.is_purged:
            continue
        if rec.foto_amplop_path and os.path.exists(rec.foto_amplop_path):
            try:
                os.remove(rec.foto_amplop_path)
                files_removed += 1
            except OSError as exc:
                logger.warning("Gagal hapus file %s: %s", rec.foto_amplop_path, exc)

        rec.nama_umat_encrypted = None
        rec.nomor_whatsapp_encrypted = None
        rec.foto_amplop_path = "PURGED"
        rec.is_purged = True
        purged_count += 1

    db.commit()
    return {
        "status": "OK",
        "cutoff_date": cutoff.isoformat(),
        "purged_count": purged_count,
        "files_removed": files_removed,
    }
