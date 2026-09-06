"""
FLIPUS v1.5 — FASE 2 S5+R4 + S7: schema migration & backfill porsi Uni.

Langkah:
  1. ALTER TABLE kuitansi ADD COLUMN porsi_x_uni, porsi_pt_uni, porsi_khusus_uni
     (BigInteger, default 0). Untuk SQLite, kalau kolom sudah ada → di-skip.
  2. Backfill: hitung ulang porsi_uni untuk SEMUA kuitansi existing pakai
     Jerry Model B (compute_porsi) dengan PersentaseConfig MISI saat ini.
  3. Validasi konservasi: total in == total out (jemaat + misi + uni).

AMAN dijalankan berulang (idempotent).
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import text, inspect
from app.core.database import SessionLocal, engine
from app.models.transaction import Kuitansi
from app.models.persentase import PersentaseConfig
from app.models.tenant import Tenant
from app.utils.porsi_calculator import compute_porsi


def ensure_columns():
    """ALTER TABLE kalau kolom belum ada (SQLite-safe)."""
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("kuitansi")}
    bigint_cols = ["porsi_x_uni", "porsi_pt_uni", "porsi_khusus_uni"]
    datetime_cols = ["porsi_recomputed_at"]  # FASE 2 S6/R5: tracking recompute timestamp
    missing_bigint = [c for c in bigint_cols if c not in cols]
    missing_dt = [c for c in datetime_cols if c not in cols]
    if not missing_bigint and not missing_dt:
        print(f"[migrate-porsi-uni] Semua kolom sudah ada. Skip ALTER.")
        return
    with engine.begin() as conn:
        for col in missing_bigint:
            sql = f"ALTER TABLE kuitansi ADD COLUMN {col} BIGINT DEFAULT 0 NOT NULL"
            print(f"[migrate-porsi-uni] {sql}")
            conn.execute(text(sql))
        for col in missing_dt:
            # SQLite + PostgreSQL: DATETIME NULL default. Tidak ada DEFAULT karena nullable.
            sql = f"ALTER TABLE kuitansi ADD COLUMN {col} DATETIME"
            print(f"[migrate-porsi-uni] {sql}")
            conn.execute(text(sql))
    added = len(missing_bigint) + len(missing_dt)
    print(f"[migrate-porsi-uni] ✓ {added} kolom ditambahkan.")


def _resolve_config(db, tenant):
    """Ambil PersentaseConfig MISI scope untuk tenant. Fallback ke default Jerry."""
    if not tenant or not tenant.misi_konferens_id:
        # SDA doctrine: pct_x_jemaat=0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0
        return dict(pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
                    pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0)
    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == "MISI",
                PersentaseConfig.ref_id == tenant.misi_konferens_id)
        .first()
    )
    if not cfg:
        return dict(pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
                    pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0)
    return dict(pct_x_jemaat=cfg.pct_x_jemaat, pct_pt_jemaat=cfg.pct_pt_jemaat,
                pct_khusus_jemaat=cfg.pct_khusus_jemaat,
                pct_x_uni=cfg.pct_x_uni, pct_pt_uni=cfg.pct_pt_uni,
                pct_khusus_uni=cfg.pct_khusus_uni)


def backfill_porsi_uni():
    """Hitung ulang porsi_uni untuk semua kuitansi existing."""
    db = SessionLocal()
    try:
        # Cache tenant → config
        tenant_cache: dict = {}
        kuit = db.query(Kuitansi).filter(Kuitansi.is_purged == False).all()  # noqa: E712
        updated = 0
        violations = 0
        for k in kuit:
            tid = k.tenant_id
            if tid not in tenant_cache:
                tenant_cache[tid] = (
                    db.query(Tenant).filter(Tenant.id == tid).first()
                )
            tenant = tenant_cache[tid]
            cfg = _resolve_config(db, tenant)
            porsi = compute_porsi(
                x=k.perpuluhan_x_angka or 0,
                pt=k.pt_angka or 0,
                kh=k.khusus_angka or 0,
                **cfg,
            )
            old = (k.porsi_x_uni, k.porsi_pt_uni, k.porsi_khusus_uni)
            new = (porsi["pu_x"], porsi["pu_pt"], porsi["pu_kh"])
            if old != new:
                k.porsi_x_uni = new[0]
                k.porsi_pt_uni = new[1]
                k.porsi_khusus_uni = new[2]
                updated += 1
            # Validasi konservasi
            total_in = (k.perpuluhan_x_angka or 0) + (k.pt_angka or 0) + (k.khusus_angka or 0)
            total_out = (
                (k.porsi_kantor_misi or 0)
                + (k.porsi_kas_jemaat or 0)
                + (k.porsi_x_uni or 0)
                + (k.porsi_pt_uni or 0)
                + (k.porsi_khusus_uni or 0)
            )
            if total_in != total_out:
                violations += 1
                print(f"  [VIOLATION] kuitansi #{k.id}: in={total_in:,} != out={total_out:,}")
        db.commit()
        print(f"[migrate-porsi-uni] ✓ {updated} kuitansi ter-update porsi_uni")
        print(f"[migrate-porsi-uni]   Total diproses: {len(kuit)}")
        if violations:
            print(f"[migrate-porsi-uni] ⚠️  {violations} kuitansi punya conservation violation (cek manual)")
        else:
            print(f"[migrate-porsi-uni] ✓ Conservation OK untuk semua kuitansi.")
    finally:
        db.close()


def main():
    print("=== FASE 2 S5+S7: migrate_porsi_uni ===")
    ensure_columns()
    backfill_porsi_uni()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
