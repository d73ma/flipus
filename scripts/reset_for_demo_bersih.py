"""
FLIPUS — Reset & seed simulasi demo BERSIH (Model B).

Tujuan: Setelah demo pertama ke teman-teman berhasil dan mereka setuju untuk
lanjut demo final ke Uni/Daerah Misi/perwakilan jemaat, Jerry mau reset
semua kuitansi existing + tambah 4 jemaat simulasi + generate 2 sabat data.

CATATAN PENTING (2026-08-23):
- Hanya boleh dijalankan oleh Jerry (pemilik FLIPUS).
- Hapus semua Kuitansi (tapi JANGAN hapus users/tenants/units/misi).
- Tambah 2 jemaat baru (total jadi 4 jemaat, semua di Misi DK Minahasa).
- Reset PersentaseConfig ke default Model B (pct_uni = 0 untuk X/PT/KH).
- Generate 8-12 kuitansi per sabat × 2 sabat = 16-24 kuitansi total.

Cara pakai:
    cd /Users/jerrymauri/Flipus
    ./.venv/bin/python3 -m scripts.reset_for_demo_bersih

Akan menulis log ke stdout. Aman diulang (idempotent untuk tenants & pct config).
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date

# Path setup
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import delete  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import encrypt_pii, generate_tenant_signature, hash_password  # noqa: E402
from app.models.master import MisiKonferens, PersentaseConfig  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.transaction import (
    Kuitansi,  # RekapMingguan = String column on Kuitansi, no separate model  # noqa: E402
)
from app.models.user import User  # noqa: E402
from app.utils.porsi_calculator import compute_porsi  # noqa: E402

# === Konfigurasi simulasi ===
JEMAAT_BARU = [
    {"kode": "NATAAN-RAT",  "nama": "Jemaat Nataan Ratahan",  "bendahara": "Bpk. Yusuf Tamaka",  "pendeta": "Pdt. Daniel Sondakh",  "ketua": "Bpk. Stevi Kaunang"},
    {"kode": "SENTRUM-MIN", "nama": "Jemaat Sentrum Minahasa", "bendahara": "Bpk. Ferry Lolong",     "pendeta": "Pdt. Yusuf Mantik",      "ketua": "Bpk. Denny Pangkerego"},
    {"kode": "TONDANO",     "nama": "Jemaat Tondano",          "bendahara": "Ibu  Maria Wenas",      "pendeta": "Pdt. Hanny Wenas",       "ketua": "Bpk. Roy Lengkong"},
    {"kode": "BITUNG",      "nama": "Jemaat Bitung",           "bendahara": "Bpk. Hengky Mantik",    "pendeta": "Pdt. Jhonly Tuwaidan",   "ketua": "Ibu  Yanti Kalalo"},
]

# 2 sabat simulasi (Sabtunya dalam kalendar Masehi)
SABAT_SIMULASI = [
    date(2026, 8, 22),   # Sabat ke-34
    date(2026, 8, 29),   # Sabat ke-35
]

# Rentang nominal per kategori (rupiah)
NOMINAL = {
    "X":      (50_000,    2_000_000),     # Perpuluhan per orang
    "PT":     (30_000,      500_000),     # Persembahan Terpadu
    "KH":     (100_000,   5_000_000),     # Persembahan Khusus (lebih besar, lebih jarang)
}

# Jumlah umat per jemaat per sabat (variasi biar realistis)
JUMLAH_UMAT_RANGE = (3, 6)


def log(msg: str):
    print(f"[reset] {msg}", flush=True)


def reset_kuitansi(db):
    """Hapus semua kuitansi (id_rekap_mingguan adalah String column, bukan table terpisah)."""
    n_kuit = db.query(Kuitansi).count()
    log(f"Hapus {n_kuit} Kuitansi …")
    db.execute(delete(Kuitansi))
    db.commit()


def reset_pct_config(db):
    """Reset PersentaseConfig ke default Jerry Model B konservatif (KH locked 0%)."""
    log("Reset PersentaseConfig (Model B, pct_uni = 0, KH = 0) …")
    # Hapus semua pct config lama
    db.execute(delete(PersentaseConfig))
    db.commit()

    # Default MISI (DK Minahasa, ref_id=1):
    # - X 100% ke Misi → pct_x_jemaat = 0 (slider 100% to Misi)
    # - PT 50% ke Misi → pct_pt_jemaat = 0.5 (slider 50% to Misi)
    # - KH 0% locked → pct_khusus_jemaat = 0
    db.add(PersentaseConfig(
        scope="MISI", ref_id=1,
        pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
        pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
    ))
    # Default UNI (UKIKT, ref_id=1): pct_uni konservatif (0)
    db.add(PersentaseConfig(
        scope="UNI", ref_id=1,
        pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
        pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
    ))
    db.commit()


def ensure_4_jemaat(db):
    """Pastikan ada 4 jemaat di Misi Minahasa Utara dan Bitung (T92). Tambah jika kurang."""
    # T92 (2026-08-23): lookup by kode (bukan hardcoded id) supaya robust thd migrasi.
    target_misi = db.query(MisiKonferens).filter(MisiKonferens.kode == "M01_MIN_UTR_BTG").first()
    if not target_misi:
        log("  ✗ M01_MIN_UTR_BTG tidak ditemukan. Jalankan scripts/seed_ukikt_misi_proper.py dulu.")
        return
    log(f"Cek jemaat di Misi {target_misi.nama_resmi} (ref_id={target_misi.id}) …")
    existing_nama = {
        t.nama_jemaat_lokal for t in
        db.query(Tenant).filter(Tenant.misi_konferens_id == target_misi.id).all()
    }

    # Jaga 2 jemaat existing (Nataan, Sentrum), tambah 2 jemaat baru (Tondano, Bitung)
    for spec in JEMAAT_BARU:
        if spec["nama"] in existing_nama:
            log(f"  ✓ {spec['nama']} sudah ada, skip")
            continue
        sig = generate_tenant_signature(
            uni="GMAHK UKIKT",
            kantor_misi="Daerah Konferens Minahasa",
            jemaat=spec["nama"],
        )
        t = Tenant(
            nama_uni="GMAHK UKIKT",
            nama_kantor_misi="Daerah Konferens Minahasa",
            nama_jemaat_lokal=spec["nama"],
            misi_konferens_id=target_misi.id,
            nama_pendeta=spec["pendeta"],
            nama_bendahara=spec["bendahara"],
            nama_ketua_keuangan=spec["ketua"],
            tenant_signature=sig,
            status="active",
            is_active=True,
        )
        db.add(t)
        db.flush()
        # Create default Bendahara user untuk jemaat baru
        u = User(
            tenant_id=t.id,
            username=f"bendahara_{spec['kode'].lower().replace('-', '_')[:8]}",
            password_hash=hash_password("Bendahara123!"),
            nama_lengkap=spec["bendahara"],
            role="BENDAHARA",
            is_active=True,
            nomor_whatsapp="+6281234567890",  # dummy untuk demo
        )
        db.add(u)
        log(f"  + Tambah jemaat: {spec['nama']} (id={t.id})")
    db.commit()


def get_all_jemaat(db):
    """Ambil semua jemaat di Misi Minahasa Utara dan Bitung (T92) — untuk generate kuitansi."""
    target_misi = db.query(MisiKonferens).filter(MisiKonferens.kode == "M01_MIN_UTR_BTG").first()
    if not target_misi:
        return []
    return db.query(Tenant).filter(Tenant.misi_konferens_id == target_misi.id).order_by(Tenant.id).all()


def random_nominal(kategori: str) -> int:
    lo, hi = NOMINAL[kategori]
    # Round ke 5000 biar realistis (orang tidak bayar Rp 47,231)
    raw = random.randint(lo, hi)
    return round(raw / 5000) * 5000


def generate_kuitansi_per_sabat(db, tanggal_sabat: date, pct: dict, jemaats: list):
    """Generate kuitansi untuk 1 tanggal sabat di semua jemaat."""
    log(f"Generate kuitansi untuk Sabat {tanggal_sabat} …")
    total_sabat = 0

    # id_rekap_mingguan = String ID per (tenant, tanggal) — format: RK-YYYY-MM-DD
    id_rekap = f"RK-{tanggal_sabat.strftime('%Y-%m-%d')}"

    for jemaat in jemaats:
        # Generate 3-6 kuitansi per jemaat per sabat
        n_umat = random.randint(*JUMLAH_UMAT_RANGE)
        for urutan in range(1, n_umat + 1):
            total_x = random_nominal("X") if random.random() > 0.2 else 0  # 80% ada X
            total_pt = random_nominal("PT") if random.random() > 0.5 else 0  # 50% ada PT
            total_kh = random_nominal("KH") if random.random() > 0.7 else 0  # 30% ada KH
            if total_x == 0 and total_pt == 0 and total_kh == 0:
                total_x = random_nominal("X") // 2  # minimal 1 nominal
            total_all = total_x + total_pt + total_kh

            # Hitung porsi Model B
            p = compute_porsi(
                x=total_x, pt=total_pt, kh=total_kh,
                pct_x_jemaat=pct["pct_x_jemaat"],
                pct_pt_jemaat=pct["pct_pt_jemaat"],
                pct_khusus_jemaat=pct["pct_khusus_jemaat"],
                pct_x_uni=pct["pct_x_uni"],
                pct_pt_uni=pct["pct_pt_uni"],
                pct_khusus_uni=pct["pct_khusus_uni"],
            )
            # Ambil nama dummy
            nama_nomor = urutan
            nama_umat = f"Umat {nama_nomor:02d}"

            k = Kuitansi(
                tenant_id=jemaat.id,
                id_rekap_mingguan=id_rekap,
                nomor_kuitansi=f"{tanggal_sabat.strftime('%Y%m%d')}-{jemaat.id:03d}-{urutan:03d}",
                tanggal_sabat=tanggal_sabat,
                nama_umat_encrypted=encrypt_pii(nama_umat),
                nomor_whatsapp_encrypted=encrypt_pii(f"+628120000{urutan:04d}"),
                foto_amplop_path=None,
                perpuluhan_x_angka=total_x,
                pt_angka=total_pt,
                khusus_angka=total_kh,
                total_pemberian_angka=total_all,
                total_pemberian_huruf="",  # computed on-the-fly by frontend
                porsi_kantor_misi=p["pm_x"] + p["pm_pt"],
                porsi_kas_jemaat=(p["pj_x"] + p["pj_pt"]) + p["pj_kh"],
                porsi_khusus_misi=p["pm_kh"],
                porsi_khusus_jemaat=p["pj_kh"] + p["pu_kh"],  # KH share jemaat + uni (Model B)
                status="finalized",
                is_purged=False,
            )
            db.add(k)
            total_sabat += 1
    db.commit()
    return total_sabat


def main():
    log("=" * 60)
    log("FLIPUS Reset & Seed Demo Bersih (Model B)")
    log("=" * 60)

    # Ensure schema up-to-date (idempotent)
    Base.metadata.create_all(bind=engine)

    random.seed(42)  # reproducible untuk demo

    db = SessionLocal()
    try:
        # Step 1: Reset kuitansi existing
        reset_kuitansi(db)

        # Step 2: Reset pct config
        reset_pct_config(db)

        # Step 3: Ensure 4 jemaat
        ensure_4_jemaat(db)

        # Step 4: Generate data simulasi 2 sabat
        log("Generate 2 sabat simulasi …")
        # Jerry Model B: pct_uni applied to TOTAL.
        # Default MISI: X 100%→Misi (pj=0), PT 50%→Misi (pj=0.5), KH 0 locked.
        # Default UNI: pct_uni = 0 konservatif (Jerry set manual via UI).
        pct = {
            "pct_x_jemaat": 0.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.0,
            "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0,
        }
        jemaats = get_all_jemaat(db)
        log(f"  Total jemaat di Misi DK Minahasa: {len(jemaats)}")
        total_kuit = 0
        for sabat in SABAT_SIMULASI:
            n = generate_kuitansi_per_sabat(db, sabat, pct, jemaats)
            total_kuit += n
        log(f"Total kuitansi ter-generate: {total_kuit}")

        log("=" * 60)
        log("✓ Reset & seed selesai. Database siap untuk demo final.")
        log("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
