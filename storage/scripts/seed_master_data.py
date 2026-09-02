"""
FLIPUS v1.1 — Seed master data Uni + Misi/Konferens sesuai spec user.

Distribution (12 total: 3 Konferens + 9 Misi):
- UIKT: 3 Konferens (DKM, DMML, DKSST)
- UIKB: 3 Misi (DBMG, DST, DLTT) + 1 Misi (DM Maluku)
- UIKC: 5 Misi (DMKB, DP, DNU, DPB, DPBD, DPT)

Jalankan di Mac:
    /Users/jerrymauri/Flipus/.venv/bin/python3 -m storage.scripts.seed_master_data
"""

import os
import sys

sys.path.insert(0, os.getcwd())

from app.core.database import SessionLocal, Base, engine
from app.models.master import Uni, MisiKonferens


UNI_MASTER = [
    ("UIKT", "Gereja Masehi Advent Hari Ketujuh Uni Konferens Indonesia Kawasan Timur"),
    ("UIKB", "Gereja Masehi Advent Hari Ketujuh Uni Indonesia Kawasan Barat"),
    ("UIKC", "Gereja Masehi Advent Hari Ketujuh Uni Indonesia Kawasan Tengah"),
]

MISI_MASTER = [
    # ===== UIKT: 3 Konferens =====
    ("DKM",   "Daerah Konferens Minahasa",                              "KONFERENS", "UIKT"),
    ("DMML",  "Daerah Konferens Manado & Maluku Utara",                 "KONFERENS", "UIKT"),
    ("DKSST", "Daerah Konferens Sulawesi Selatan, Barat dan Tenggara",  "KONFERENS", "UIKT"),
    # ===== UIKB: 4 Misi =====
    ("DBMG",  "Daerah Misi Bolmong, Modoinding & Gorontalo",             "MISI",      "UIKB"),
    ("DST",   "Daerah Misi Sulawesi Tengah",                              "MISI",      "UIKB"),
    ("DLTT",  "Daerah Misi Luwu Tanah Toraja",                            "MISI",      "UIKB"),
    ("DM",    "Daerah Misi Maluku",                                       "MISI",      "UIKB"),
    # ===== UIKC: 5 Misi =====
    ("DMKB",  "Daerah Misi Minahasa & Kota Bitung",                       "MISI",      "UIKC"),
    ("DP",    "Daerah Misi Papua",                                        "MISI",      "UIKC"),
    ("DNU",   "Daerah Misi Nusa Utara",                                   "MISI",      "UIKC"),
    ("DPB",   "Daerah Misi Papua Barat",                                  "MISI",      "UIKC"),
    ("DPBD",  "Daerah Misi Papua Barat Daya",                             "MISI",      "UIKC"),
    # Total: 3 Konferens + 9 Misi = 12 ✓
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("=== SEED MASTER DATA ===")
    print(f"Total entries: {len(UNI_MASTER)} Uni, {len(MISI_MASTER)} Misi\n")

    # Seed Uni
    uni_map = {}
    for kode, nama in UNI_MASTER:
        existing = db.query(Uni).filter(Uni.kode == kode).first()
        if existing:
            uni_map[kode] = existing
            print(f"SKIP Uni (exists): {kode}")
            continue
        u = Uni(kode=kode, nama_resmi=nama)
        db.add(u)
        db.flush()
        uni_map[kode] = u
        print(f"INSERT Uni: {kode} - {nama}")

    # Seed Misi/Konferens
    inserted = 0
    skipped = 0
    for kode, nama, jenis, uni_kode in MISI_MASTER:
        existing = db.query(MisiKonferens).filter(MisiKonferens.kode == kode).first()
        if existing:
            print(f"SKIP Misi (exists): {kode}")
            skipped += 1
            continue
        uni = uni_map.get(uni_kode)
        if not uni:
            print(f"WARN: Uni {uni_kode} not found, skipping {kode}")
            skipped += 1
            continue
        m = MisiKonferens(kode=kode, nama_resmi=nama, jenis=jenis, uni_id=uni.id)
        db.add(m)
        print(f"INSERT Misi: {kode} - {nama} (uni={uni_kode})")
        inserted += 1

    db.commit()
    print(f"\nDONE: {inserted} inserted, {skipped} skipped")
    db.close()


if __name__ == "__main__":
    main()
