"""
T111 inspect (2026-08-26): Cek di mana data staging lama tersimpan.
Lihat row yang tanggal_sabat-nya BUKAN sabat berjalan, untuk verifikasi
bahwa data lama tidak hilang (cuma salah tanggal).

Usage:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 scripts/inspect_staging_old.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models.transaction import Kuitansi  # noqa: E402


def main():
    db = SessionLocal()
    try:
        # Sabat berjalan saat ini
        from app.utils.sabat_counter import get_sabat_info
        sabat_tgl = get_sabat_info()["tanggal_sabat"]
        print(f"Sabat berjalan saat ini: {sabat_tgl}\n")

        # Group semua kuitansi finalized by tanggal_sabat
        rows = (
            db.query(Kuitansi)
            .filter(Kuitansi.is_finalized.is_(True), Kuitansi.status == "finalized")
            .all()
        )
        by_date: dict[str, list[Kuitansi]] = {}
        for k in rows:
            by_date.setdefault(k.tanggal_sabat, []).append(k)

        print("Rekap per tanggal_sabat:")
        for d in sorted(by_date.keys(), reverse=True):
            mark = " ← SABAT BERJALAN" if d == sabat_tgl else " ← BUKAN sabat berjalan (cek manual)"
            print(f"  {d}: {len(by_date[d])} kuitansi{mark}")
            for k in by_date[d][:3]:
                print(f"    id={k.id} nomor={k.nomor_kuitansi} tenant={k.tenant_id}")

        # Highlight rows yang bukan di sabat berjalan (data lama staging WA)
        stale = [k for k in rows if k.tanggal_sabat != sabat_tgl]
        print(f"\n⚠️  {len(stale)} kuitansi finalized tapi tanggal_sabat != sabat berjalan")
        if stale:
            print("   Jalankan scripts/backfill_t110_tanggal_staging.py untuk migrate ke sabat berjalan.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
