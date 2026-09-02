"""
FLIPUS — One-time migration: fix KH porsi in existing kuitansi.

Akar: rumus lama pakai pj_kh = kh * pct_khusus_jemaat (yang 0 → 0 ke Jemaat,
sisanya ke Misi). Rumus baru: pct_khusus_jemaat = fraction to MISI (semantik
terbalik dari X/PT). Jadi pct=0 → 100% stays in Jemaat.

Efek pada kuitansi existing:
  Lama: pj_kh=0, pm_kh=kh   (KH leak ke Misi)
  Baru: pj_kh=kh, pm_kh=0   (KH stays di Jemaat — sesuai Jerry lock 0%)

Script ini recompute porsi_khusus_jemaat & porsi_khusus_misi di setiap
kuitansi existing, dengan asumsi pct_khusus_jemaat=0 dan pct_khusus_uni=0
(default lock).

AMAN dijalankan berulang (idempotent).
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import update
from app.core.database import SessionLocal
from app.models.transaction import Kuitansi


def main():
    db = SessionLocal()
    try:
        kuit = db.query(Kuitansi).all()
        n = 0
        for k in kuit:
            kh = int(k.khusus_angka or 0)
            if kh == 0:
                continue
            # KH stays in Jemaat (pct_khusus_jemaat=0 = 0% ke Misi)
            new_pj_kh = kh
            new_pm_kh = 0
            new_pu_kh = 0
            if (
                k.porsi_khusus_jemaat != new_pj_kh
                or k.porsi_khusus_misi != new_pm_kh
            ):
                k.porsi_khusus_jemaat = new_pj_kh
                k.porsi_khusus_misi = new_pm_kh
                n += 1
        db.commit()
        print(f"[migrate-kh] ✓ {n} kuitansi diupdate (KH stays di Jemaat, 0 ke Misi)")
        print(f"[migrate-kh] Total kuitansi diproses: {len(kuit)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()