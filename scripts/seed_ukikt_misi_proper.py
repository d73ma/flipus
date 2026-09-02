"""
T92 — Tambah daftar Daerah Konferens + Misi untuk UKIKT sesuai urutan Jerry (2026-08-23).

3 Daerah Konferens:
  1. Daerah Konferens Manado dan Maluku Utara
  2. Daerah Konferens Minahasa
  3. Daerah Konferens Makassar

10 Daerah Misi (Minahasa → Papua):
  4. Daerah Misi Minahasa Utara dan Bitung
  5. Daerah Misi Bolaang Mongondow, Modoinding, dan Gorontalo
  6. Daerah Misi Sulawesi Tengah
  7. Daerah Misi Luwu Tanah Toraja
  8. Daerah Misi Nusa Utara
  9. Daerah Misi Maluku
  10. Daerah Misi Papua
  11. Daerah Misi Papua Barat
  12. Daerah Misi Papua Barat Daya
  13. Daerah Misi Papua Tengah

Idempotent — aman jalan berulang. Tidak hapus data existing.

Strategi ordering:
- Master endpoint pakai `order_by(jenis, kode)`. KONFERENS < MISI alphabetically.
- Pakai kode prefix K01..K03 untuk Konferens (urut sesuai Jerry), M01..M10 untuk Misi.
- Dropdown akan otomatis tampil sesuai urutan ini.

Backward compat:
- Existing DK.MIN dan DK.MIN.SEL (placeholder) di-rename jadi ZZZ_LEGACY_*.
- Existing tenant demo (Nataan Ratahan, Sentrum Minahasa) yang refer ke DK.MIN
  dimigrasi ke M01_MIN_UTR_BTG (Daerah Misi Minahasa Utara dan Bitung) —
  geografis lebih akurat.

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/seed_ukikt_misi_proper.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, engine, SessionLocal
from app.models.master import Uni, MisiKonferens, PersentaseConfig
from app.models.tenant import Tenant


# Daftar 13 entry sesuai urutan Jerry (KONFERENS dulu, baru MISI)
UKIKT_MISI_KONFERENS = [
    ("K01_MAN_MALUT", "Daerah Konferens Manado dan Maluku Utara", "KONFERENS"),
    ("K02_MIN", "Daerah Konferens Minahasa", "KONFERENS"),
    ("K03_MAK", "Daerah Konferens Makassar", "KONFERENS"),
]

UKIKT_MISI_LIST = [
    ("M01_MIN_UTR_BTG", "Daerah Misi Minahasa Utara dan Bitung", "MISI"),
    ("M02_BMG", "Daerah Misi Bolaang Mongondow, Modoinding, dan Gorontalo", "MISI"),
    ("M03_SULTENG", "Daerah Misi Sulawesi Tengah", "MISI"),
    ("M04_LUTRA", "Daerah Misi Luwu Tanah Toraja", "MISI"),
    ("M05_NUSA_UTARA", "Daerah Misi Nusa Utara", "MISI"),
    ("M06_MALUKU", "Daerah Misi Maluku", "MISI"),
    ("M07_PAPUA", "Daerah Misi Papua", "MISI"),
    ("M08_PAPUA_BARAT", "Daerah Misi Papua Barat", "MISI"),
    ("M09_PAPUA_BARAT_DAYA", "Daerah Misi Papua Barat Daya", "MISI"),
    ("M10_PAPUA_TENGAH", "Daerah Misi Papua Tengah", "MISI"),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ===== Cari Uni UKIKT =====
        uni = db.query(Uni).filter(Uni.kode == "UKIKT").first()
        if not uni:
            print("✗ Uni GMAHK UKIKT belum ada. Jalankan scripts/seed_demo.py dulu.")
            return

        # ===== Rename existing placeholder ke ZZZ_LEGACY (idempotent) =====
        legacy_remap = [
            ("DK.MIN", "ZZZ_LEGACY_DK_MIN", "(LEGACY) Misi DK Minahasa — lihat M01_MIN_UTR_BTG"),
            ("DK.MIN.SEL", "ZZZ_LEGACY_DK_MIN_SEL", "(LEGACY) Misi DK Minahasa Selatan"),
        ]
        for old_kode, new_kode, new_nama in legacy_remap:
            existing = db.query(MisiKonferens).filter(MisiKonferens.kode == old_kode).first()
            if existing:
                # Cek apakah kode baru sudah dipakai
                if not db.query(MisiKonferens).filter(MisiKonferens.kode == new_kode).first():
                    existing.kode = new_kode
                    existing.nama_resmi = new_nama
                    db.commit()
                    print(f"  ↻ Renamed: {old_kode} → {new_kode}")
                else:
                    print(f"  · Sudah ada {new_kode} (skip rename {old_kode})")
            else:
                print(f"  · {old_kode} tidak ditemukan (skip)")

        # ===== Insert 3 Konferens =====
        print("\n→ Konferens:")
        for kode, nama, jenis in UKIKT_MISI_KONFERENS:
            existing = db.query(MisiKonferens).filter(MisiKonferens.kode == kode).first()
            if not existing:
                m = MisiKonferens(kode=kode, nama_resmi=nama, jenis=jenis, uni_id=uni.id)
                db.add(m)
                db.commit()
                db.refresh(m)
                print(f"  ✓ Konferens created: {m.nama_resmi} (kode={m.kode})")
            else:
                print(f"  · Konferens exists: {existing.nama_resmi} (kode={existing.kode})")

        # ===== Insert 10 Misi =====
        print("\n→ Misi:")
        for kode, nama, jenis in UKIKT_MISI_LIST:
            existing = db.query(MisiKonferens).filter(MisiKonferens.kode == kode).first()
            if not existing:
                m = MisiKonferens(kode=kode, nama_resmi=nama, jenis=jenis, uni_id=uni.id)
                db.add(m)
                db.commit()
                db.refresh(m)
                print(f"  ✓ Misi created: {m.nama_resmi} (kode={m.kode})")
            else:
                print(f"  · Misi exists: {existing.nama_resmi} (kode={existing.kode})")

            # PersentaseConfig per Misi (scope=MISI) — idempotent
            ref_id = existing.id if existing else m.id
            cfg = (
                db.query(PersentaseConfig)
                .filter(PersentaseConfig.scope == "MISI", PersentaseConfig.ref_id == ref_id)
                .first()
            )
            if not cfg:
                cfg = PersentaseConfig(
                    scope="MISI",
                    ref_id=ref_id,
                    pct_x_jemaat=0.0,       # 0% X tinggal di Jemaat → 100% X ke Misi (SDA tithe doctrine)
                    pct_pt_jemaat=0.5,
                    pct_khusus_jemaat=0.0,
                )
                db.add(cfg)
                db.commit()
                print(f"    ✓ PersentaseConfig MISI/{kode} created")

        # ===== Migrate existing tenant demo dari DK.MIN ke M01_MIN_UTR_BTG =====
        print("\n→ Migrasi tenant demo (DK.MIN → M01_MIN_UTR_BTG):")
        legacy = db.query(MisiKonferens).filter(MisiKonferens.kode == "ZZZ_LEGACY_DK_MIN").first()
        new_misi = db.query(MisiKonferens).filter(MisiKonferens.kode == "M01_MIN_UTR_BTG").first()
        if legacy and new_misi:
            migrated = 0
            for t in db.query(Tenant).filter(Tenant.misi_konferens_id == legacy.id).all():
                t.misi_konferens_id = new_misi.id
                migrated += 1
                print(f"  ↻ {t.nama_jemaat_lokal}: id_misi {legacy.id} → {new_misi.id}")
            db.commit()
            print(f"  ✓ {migrated} tenant dimigrasi ke M01_MIN_UTR_BTG")
        else:
            print(f"  · Skip migrasi (legacy={legacy is not None}, new_misi={new_misi is not None})")

        # ===== Summary =====
        print("\n✓ Selesai. Daftar Daerah Konferens + Misi untuk UKIKT (urut dropdown):")
        rows = (
            db.query(MisiKonferens)
            .filter(MisiKonferens.uni_id == uni.id)
            .order_by(MisiKonferens.jenis, MisiKonferens.kode)
            .all()
        )
        for i, r in enumerate(rows, 1):
            print(f"  {i:2}. [{r.jenis:9}] {r.kode:24} — {r.nama_resmi}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()