"""
T101 fix — pct_x_jemaat=1.0 di seed scripts SALAH untuk tithe GMAHK.

Bug:
- pct_x_jemaat=1.0 artinya 100% X (perpuluhan/tithe) tinggal di Jemaat, 0% ke Misi.
- Per doktrin SDA/GMAHK, tithe HARUS 100% ke Kantor Misi.
- Padahal formula Jerry Model B sudah benar: pj=total×pct_jemaat, pm=total−pj−pu.
- Yang salah hanya nilai default pct_x_jemaat=1.0 di 3 seed scripts.

Fix:
1. UPDATE PersentaseConfig.pct_x_jemaat=0.0 untuk semua baris yang masih > 0.
   pct_x_uni TETAP (preserve setting Admin Uni/Auditor yang existing).
2. Recompute porsi semua Kuitansi existing yang X > 0, pakai config baru.

Idempotent — aman run multiple kali.

Usage:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 scripts/fix_pct_x_jemaat_t101.py
"""
import logging
import sys
from pathlib import Path

# Add project root to sys.path so 'app' import works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.models.master import PersentaseConfig
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.utils.porsi_calculator import compute_porsi

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("fix_pct_x_jemaat_t101")


def main():
    db = SessionLocal()

    log.info("=" * 60)
    log.info("T101 fix: pct_x_jemaat bug")
    log.info("=" * 60)

    # ===== STEP 1: Audit PersentaseConfig =====
    cfgs_all = db.query(PersentaseConfig).all()
    log.info(f"\n[1/3] Audit PersentaseConfig ({len(cfgs_all)} rows):")
    cfg_affected = []
    for c in cfgs_all:
        marker = " ⚠ NEEDS FIX" if c.pct_x_jemaat > 0 else " ✓ OK"
        log.info(
            f"  {c.scope}/ref={c.ref_id}: x={c.pct_x_jemaat} pt={c.pct_pt_jemaat} "
            f"kh={c.pct_khusus_jemaat} | x_uni={c.pct_x_uni or 0} "
            f"pt_uni={c.pct_pt_uni or 0}{marker}"
        )
        if c.pct_x_jemaat > 0:
            cfg_affected.append(c)

    if not cfg_affected:
        log.info("\n  All pct_x_jemaat already 0 — no DB update needed.")
    else:
        log.info(f"\n  Found {len(cfg_affected)} rows with pct_x_jemaat > 0. Fixing...")
        for c in cfg_affected:
            old = c.pct_x_jemaat
            c.pct_x_jemaat = 0.0
            log.info(f"    {c.scope}/ref={c.ref_id}: pct_x_jemaat {old} → 0.0")
        db.commit()
        log.info("  ✓ PersentaseConfig updated.")

    # ===== STEP 2: Build config map =====
    log.info("\n[2/3] Building config map (MISI scope)...")
    config_map = {}
    for c in db.query(PersentaseConfig).filter(PersentaseConfig.scope == "MISI").all():
        config_map[c.ref_id] = {
            "pct_x_jemaat": c.pct_x_jemaat,
            "pct_pt_jemaat": c.pct_pt_jemaat,
            "pct_khusus_jemaat": c.pct_khusus_jemaat,
            "pct_x_uni": c.pct_x_uni or 0.0,
            "pct_pt_uni": c.pct_pt_uni or 0.0,
            "pct_khusus_uni": c.pct_khusus_uni or 0.0,
        }
    log.info(f"  Loaded {len(config_map)} MISI configs.")

    # ===== STEP 3: Recompute Kuitansi =====
    log.info("\n[3/3] Recomputing Kuitansi rows with X > 0...")
    ks = db.query(Kuitansi).filter(Kuitansi.perpuluhan_x_angka > 0).all()
    log.info(f"  Found {len(ks)} rows.")

    # Cache tenants
    tenant_cache = {}
    def get_tenant(tid: int) -> Tenant | None:
        if tid not in tenant_cache:
            tenant_cache[tid] = db.query(Tenant).filter(Tenant.id == tid).first()
        return tenant_cache[tid]

    fixed_count = 0
    skipped_count = 0
    for k in ks:
        tenant = get_tenant(k.tenant_id)
        if not tenant or not tenant.misi_konferens_id:
            log.warning(f"  Skip k={k.nomor_kuitansi}: tenant/misi missing")
            skipped_count += 1
            continue

        cfg = config_map.get(tenant.misi_konferens_id)
        if not cfg:
            log.warning(
                f"  Skip k={k.nomor_kuitansi}: no config for misi={tenant.misi_konferens_id}"
            )
            skipped_count += 1
            continue

        # Recompute
        p = compute_porsi(
            x=k.perpuluhan_x_angka,
            pt=k.pt_angka,
            kh=k.khusus_angka or 0,
            **cfg,
        )

        old_jemaat = k.porsi_kas_jemaat
        old_misi = k.porsi_kantor_misi
        old_kh_jemaat = k.porsi_khusus_jemaat
        old_kh_misi = k.porsi_khusus_misi

        k.porsi_kantor_misi = p["pm_x"] + p["pm_pt"]
        k.porsi_kas_jemaat = (p["pj_pt"] + p["pj_x"]) + p["pj_kh"]
        k.porsi_khusus_misi = p["pm_kh"]
        k.porsi_khusus_jemaat = p["pj_kh"] + p["pu_kh"]

        log.info(
            f"  k={k.nomor_kuitansi} (tenant={tenant.nama_jemaat_lokal}): "
            f"jemaat {old_jemaat:,} → {k.porsi_kas_jemaat:,}, "
            f"misi {old_misi:,} → {k.porsi_kantor_misi:,}, "
            f"kh_jemaat {old_kh_jemaat:,} → {k.porsi_khusus_jemaat:,}, "
            f"kh_misi {old_kh_misi:,} → {k.porsi_khusus_misi:,}"
        )
        fixed_count += 1

    db.commit()
    log.info(f"\n  ✓ Recomputed {fixed_count} rows, skipped {skipped_count}.")

    log.info("\n" + "=" * 60)
    log.info("DONE. Re-run idempotent (no-op kalau sudah fixed).")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
