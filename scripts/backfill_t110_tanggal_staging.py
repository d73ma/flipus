"""
T110 (2026-08-26): Backfill tanggal_sabat finalized staging items ke sabat 34,
tanggal 2026-08-22 (sesuai permintaan Jerry).

Item hasil 'Simpan Semua' SEBELUM T110 fix punya tanggal_sabat = tanggal input
WA (mis. 2026-08-24). Update jadi 2026-08-22 supaya match dengan tabel
'Persembahan Sabat Ini' yang filter sabat_berjalan.

Usage:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 scripts/backfill_t110_tanggal_staging.py
"""
import sys
from pathlib import Path

# Add project root ke sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.transaction import Kuitansi  # noqa: E402

# T110: target tanggal — Sabat ke-34, 22 Agustus 2026 (per Jerry 2026-08-26)
TARGET_TANGGAL = "2026-08-22"


def main():
    db: Session = SessionLocal()
    try:
        sabat_tgl = TARGET_TANGGAL
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).all()
        total_updated = 0
        for t in tenants:
            # Cari Kuitansi finalized di tenant ini yang tanggal_sabat != sabat_tgl
            rows = (
                db.query(Kuitansi)
                .filter(
                    Kuitansi.tenant_id == t.id,
                    Kuitansi.is_finalized.is_(True),
                    Kuitansi.status == "finalized",
                    Kuitansi.tanggal_sabat != sabat_tgl,
                )
                .all()
            )
            for k in rows:
                old = k.tanggal_sabat
                k.tanggal_sabat = sabat_tgl
                print(f"  tenant={t.id} kuitansi={k.id} {old} → {sabat_tgl}")
                total_updated += 1
        db.commit()
        print(f"\n✅ {total_updated} kuitansi updated to sabat_tgl={sabat_tgl}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
