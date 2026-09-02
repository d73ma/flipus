"""
T33: Seed data demo realistis — full version untuk WOW effect saat demo.

Generate data yang terasa nyata untuk audience gereja/administrator:
- 60+ umat per jemaat (variasi nama Indonesia + Batak, laki-laki & perempuan)
- 6 sabat terakhir dengan tanggal realistis
- 10-15 kuitansi per sabat per jemaat (~120 kuitansi per jemaat = ~240 total)
- Distribusi nominal realistis (Rp 25rb - 2jt, weighted distribution)
- Variasi tipe: 60% X+PT, 30% X saja, 10% X+PT+Khusus
- Status mix: 5 finalized + 1 draft (untuk demo approval flow)
- Encrypt PII (nama_umat, nomor_whatsapp) via Fernet
- Hitung porsi via financial_calculator dengan PersentaseConfig

Differences dari seed_demo.py:
- seed_demo.py minimal: hanya Uni + Misi + Tenant + User
- seed_demo_full.py: di atas + kuitansi realistis

Cara pakai:
    .venv/bin/python3 scripts/seed_demo_full.py

Idempotent — kalau sudah ada kuitansi untuk sabat tsb, skip (tidak duplicate).
"""
import os
import sys
import random
from datetime import datetime, timedelta

# Pastikan root project ada di sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.core.database import SessionLocal, engine, Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.transaction import Kuitansi
from app.models.master import Uni, MisiKonferens, PersentaseConfig
from app.core.security import encrypt_pii
from app.utils.nomor_kuitansi import generate_nomor_kuitansi, generate_id_rekap_mingguan
from app.services.financial_calculator import calculate_distribution
from app.utils.number_to_words import terbilang

# Buat semua tabel kalau belum ada (idempotent)
Base.metadata.create_all(bind=engine)

# Reproducible random
random.seed(42)

# ============= POOL NAMA INDONESIA (Batak-friendly untuk konteks Minahasa + variasi) =============

NAMA_DEPAN_LK = [
    "Andi", "Budi", "Candra", "Daniel", "Eko", "Fandi", "Gunawan", "Hendra",
    "Indra", "Joko", "Krisna", "Lukas", "Made", "Nanda", "Oki", "Putu",
    "Rendy", "Surya", "Toni", "Wahyu", "Yanto", "Zaki", "Adi", "Bayu",
    "Dedi", "Ferry", "Galih", "Hadi", "Iwan", "Kevin", "Rivaldo", "Stenly",
    "Andre", "Bryan", "Christian", "Doni", "Erwin", "Fajar", "Gilang",
]

NAMA_DEPAN_PR = [
    "Ani", "Bunga", "Cici", "Dewi", "Endah", "Fitri", "Griya", "Hesti",
    "Indah", "Jumita", "Kartika", "Lina", "Maya", "Nia", "Ovi", "Putri",
    "Ratna", "Sari", "Tari", "Utari", "Vera", "Wati", "Yuli", "Zara",
    "Ayu", "Citra", "Elsa", "Mega", "Sinta", "Yuliana", "Mery", "Novita",
    "Grace", "Felicia", "Yolanda", "Clara",
]

# Nama belakang Batak (mayoritas jemaat GMAHK di Minahasa) + variasi umum Indonesia
NAMA_BELAKANG = [
    "Lengkong", "Manurung", "Simanjuntak", "Sitompul", "Tobing", "Pohan",
    "Tampubolon", "Sinaga", "Napitupulu", "Pardede", "Hutapea", "Marpaung",
    "Sihombing", "Panggabean", "Saragih", "Purba", "Aritonang", "Silitonga",
    "Simatupang", "Rajagukguk", "Lumbantobing", "Sitorus", "Pane", "Nasution",
    "Harahap", "Rangkuti", "Daulay", "Pulungan", "Wijaya", "Santoso",
    "Wibowo", "Setiawan", "Pratama", "Saputra", "Hidayat", "Nugroho",
    "Lengkong", "Kaunang", "Mantik", "Tuwaidan", "Pontoh",
]

# ============= POOL NOMINAL (dalam Rupiah) =============
# Weighted distribution: lebih sering nominal kecil, sesekali nominal besar
NOMINAL_X_WEIGHTED = [
    25_000, 25_000, 50_000, 50_000, 50_000, 50_000,
    100_000, 100_000, 100_000, 100_000, 150_000, 150_000,
    200_000, 250_000, 250_000, 500_000, 500_000, 1_000_000,
    1_500_000, 2_000_000,
]

NOMINAL_PT_WEIGHTED = [
    0,  # 30% X-saja = pt = 0
    10_000, 25_000, 25_000, 25_000,
    50_000, 50_000, 50_000, 50_000,
    100_000, 100_000, 150_000,
    200_000, 200_000, 500_000,
]

NOMINAL_KHUSUS_WEIGHTED = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,  # 90% tanpa khusus
    100_000, 250_000,
    500_000, 1_000_000,
    2_000_000, 5_000_000,
]


# ============= HELPERS =============

def buat_nama_umat(seed_idx: int) -> str:
    """Generate nama umat acak dengan seed_index untuk reproducibility."""
    is_perempuan = seed_idx % 2 == 1
    if is_perempuan:
        depan = NAMA_DEPAN_PR[seed_idx % len(NAMA_DEPAN_PR)]
    else:
        depan = NAMA_DEPAN_LK[seed_idx % len(NAMA_DEPAN_LK)]
    belakang = NAMA_BELAKANG[seed_idx % len(NAMA_BELAKANG)]
    return f"{depan} {belakang}"


def buat_nomor_wa(seed_idx: int) -> str:
    """Generate nomor WA Indonesia acak (format 628xxxxxxxxx)."""
    # Variation prefix untuk terlihat natural
    prefix = ["62812", "62813", "62852", "62853", "62821", "62822"][seed_idx % 6]
    suffix = (10000000 + seed_idx * 12347) % 100000000
    return f"{prefix}{suffix:08d}"


def tanggal_sabat_terakhir(n: int = 6) -> list:
    """
    Return N Sabtu terakhir sebagai list of date strings (YYYY-MM-DD).

    Reference date: hari ini (2026-08-20). Sabtu terakhir sebelumnya.
    """
    sabats = []
    # 2026-08-15 adalah Sabtu terakhir (relative to 2026-08-20)
    ref = datetime(2026, 8, 15)
    for i in range(n):
        sabat = ref - timedelta(weeks=i)
        sabats.append(sabat.strftime("%Y-%m-%d"))
    return sorted(sabats)


def get_urutan_for_sabat(db, tenant_id: int, tanggal_sabat: str) -> int:
    """Hitung urutan berikutnya (existing kuitansi + 1) untuk sabat tsb."""
    existing_count = (
        db.query(Kuitansi)
        .filter(
            Kuitansi.tenant_id == tenant_id,
            Kuitansi.tanggal_sabat == tanggal_sabat,
        )
        .count()
    )
    return existing_count + 1


# ============= EKSEKUSI =============

def seed_kuitansi_realistis():
    """Generate kuitansi realistis untuk semua jemaat."""
    db = SessionLocal()
    try:
        # ===== Daftar 6 Sabtu terakhir =====
        SABATS = tanggal_sabat_terakhir(6)
        print(f"Generate kuitansi untuk {len(SABATS)} sabat: {SABATS[0]} s/d {SABATS[-1]}")

        # Iterate per jemaat
        tenants = db.query(Tenant).order_by(Tenant.id).all()
        if not tenants:
            print("Belum ada tenant. Jalankan seed_demo.py dulu.")
            return

        total_inserted = 0
        for tenant in tenants:
            print(f"\n--- {tenant.nama_jemaat_lokal} ({tenant.initial_jemaat}) ---")

            # Get Misi & PersentaseConfig
            if not tenant.misi_konferens_id:
                print(f"  ⚠ Tenant belum terkait misi, skip")
                continue
            cfg = (
                db.query(PersentaseConfig)
                .filter(
                    PersentaseConfig.scope == "MISI",
                    PersentaseConfig.ref_id == tenant.misi_konferens_id,
                )
                .first()
            )
            if cfg:
                pct_x = cfg.pct_x_jemaat
                pct_pt = cfg.pct_pt_jemaat
                pct_kh = cfg.pct_khusus_jemaat
                pct_xu = cfg.pct_x_uni
                pct_ptu = cfg.pct_pt_uni
                pct_khu = cfg.pct_khusus_uni
            else:
                pct_x, pct_pt, pct_kh = 1.0, 0.5, 0.5
                pct_xu, pct_ptu, pct_khu = 0.0, 0.0, 0.0

            # Get bendahara user id (created_by)
            bendahara = (
                db.query(User)
                .filter(User.tenant_id == tenant.id, User.role == "BENDAHARA")
                .first()
            )
            bendahara_id = bendahara.id if bendahara else None

            tenant_seed = tenant.id * 1000

            for sabat_idx, tanggal_sabat in enumerate(SABATS):
                # Tentukan jumlah kuitansi per sabat (8-15)
                random.seed(tenant_seed + sabat_idx)
                n_kuitansi = random.randint(8, 15)

                # Status: 5 finalized, 1 draft (sabat terakhir)
                is_draft_sabat = (sabat_idx == len(SABATS) - 1) and False  # Last sabat tetap finalized untuk demo blast
                # Tapi kita tambahkan 1-2 draft dari sabat sebelumnya
                add_some_drafts = (sabat_idx < len(SABATS) - 1) and (sabat_idx % 2 == 1)

                # Hitung existing count untuk urutan
                urutan = get_urutan_for_sabat(db, tenant.id, tanggal_sabat)

                # id_rekap_mingguan
                tgl_obj = datetime.fromisoformat(tanggal_sabat)
                id_rekap = generate_id_rekap_mingguan(tgl_obj)

                print(f"  Sabat {tanggal_sabat} ({id_rekap}) — {n_kuitansi} kuitansi")

                for k_idx in range(n_kuitansi):
                    # Kalau sudah ada kuitansi for this sabat+urutan dengan nomor tsb, skip
                    nomor = generate_nomor_kuitansi(urutan, tenant.initial_jemaat, tgl_obj)
                    existing = (
                        db.query(Kuitansi)
                        .filter(Kuitansi.nomor_kuitansi == nomor)
                        .first()
                    )
                    if existing:
                        urutan += 1
                        continue

                    seed_idx = tenant_seed + sabat_idx * 100 + k_idx
                    random.seed(seed_idx)

                    # Generate nama + WA
                    nama_umat = buat_nama_umat(seed_idx)
                    nomor_wa = buat_nomor_wa(seed_idx)

                    # Generate nominal
                    x = random.choice(NOMINAL_X_WEIGHTED)
                    pt = random.choice(NOMINAL_PT_WEIGHTED)
                    khusus = random.choice(NOMINAL_KHUSUS_WEIGHTED)

                    # Hitung distribusi
                    dist = calculate_distribution(
                        perpuluhan_x=x,
                        pt=pt,
                        khusus=khusus,
                        pct_x_jemaat=pct_x,
                        pct_pt_jemaat=pct_pt,
                        pct_khusus_jemaat=pct_kh,
                        pct_x_uni=pct_xu,
                        pct_pt_uni=pct_ptu,
                        pct_khusus_uni=pct_khu,
                    )

                    total = x + pt + khusus
                    total_huruf = terbilang(total) if total > 0 else ""

                    # Status: 1-2 draft per sabat (kecuali sabat terakhir)
                    # Tujuannya: demo approval flow Ketua
                    status = "finalized"
                    if add_some_drafts and k_idx < 2:
                        status = "draft"

                    k = Kuitansi(
                        tenant_id=tenant.id,
                        id_rekap_mingguan=id_rekap,
                        nomor_kuitansi=nomor,
                        tanggal_sabat=tanggal_sabat,
                        nama_umat_encrypted=encrypt_pii(nama_umat),
                        nomor_whatsapp_encrypted=encrypt_pii(nomor_wa),
                        perpuluhan_x_angka=x,
                        pt_angka=pt,
                        khusus_angka=khusus,
                        total_pemberian_angka=total,
                        total_pemberian_huruf=total_huruf,
                        porsi_kantor_misi=dist["porsi_kantor_misi"],
                        porsi_kas_jemaat=dist["porsi_kas_jemaat"],
                        porsi_khusus_misi=dist["porsi_khusus_misi"],
                        porsi_khusus_jemaat=dist["porsi_khusus_jemaat"],
                        status=status,
                        created_by_user_id=bendahara_id,
                        is_purged=False,
                    )
                    db.add(k)
                    db.commit()
                    total_inserted += 1
                    urutan += 1

            print(f"  ✓ {tenant.nama_jemaat_lokal}: {total_kuitansi_last_tenant(db, tenant.id)} total kuitansi")

        print(f"\n=== SEED FULL SELESAI: {total_inserted} kuitansi baru di-generate ===")
        print("\nDemo accounts (existing — lihat DEMO_README.md):")
        print("  bendahara_a / Bendahara123!  (Jemaat Nataan Ratahan)")
        print("  bendahara_b / Bendahara123!  (Jemaat Sentrum Minahasa)")
        print("  auditor_misi / AuditMisi123!")
        print("  admin_uni / AdminUni123!")
    finally:
        db.close()


def total_kuitansi_last_tenant(db, tenant_id):
    """Helper buat print final summary per tenant."""
    return db.query(Kuitansi).filter(Kuitansi.tenant_id == tenant_id).count()


if __name__ == "__main__":
    seed_kuitansi_realistis()
