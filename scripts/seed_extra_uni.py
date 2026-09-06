"""
T91 — Tambah 2 Uni baru: GMAHK UIKB & GMAHK UIKT (Jerry, 2026-08-23).

Struktur Uni GMAHK (Jerry, koreksi 2026-08-23):
  - GMAHK UKIKT  = Uni Kawasan Indonesia KAWASAN TIMUR (existing, tidak diubah)
  - GMAHK UIKB   = Uni Indonesia KAWASAN BARAT (baru)
  - GMAHK UIKT   = Uni Indonesia KAWASAN TENGAH (baru)
  - Uni Kawasan Indonesia Kawasan Timur lainnya belum terbentuk

Idempotent — bisa dijalankan berulang tanpa duplikat. Tidak menghapus data existing.

Apa yang ditambah:
- Uni UIKB + 2 Misi default (DK.KALBAR, DK.SUMBAR)
- Uni UIKT + 2 Misi default (DK.JATENG, DK.KALTENG)
- PersentaseConfig per Misi (scope=MISI) dan per Uni (scope=UNI)

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/seed_extra_uni.py

Output: 2 Uni baru + 4 Misi baru + 6 PersentaseConfig baru (4 MISI + 2 UNI).
Dropdown "Pilih Uni" di /register/pendeta, /register/auditor, /register/admin
otomatis punya 3 opsi: GMAHK UKIKT, GMAHK UIKB, GMAHK UIKT.
"""

import sys
from pathlib import Path

# Pastikan root project masuk ke path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, SessionLocal, engine
from app.models.master import MisiKonferens, PersentaseConfig, Uni

UNI_DEFS = [
    {
        "kode": "UIKB",
        "nama_resmi": "GMAHK UIKB",
        "kawasan": "Barat",
        "misi_list": [
            ("DK.KALBAR", "Misi DK Kalimantan Barat", "MISI"),
            ("DK.SUMBAR", "Misi DK Sumatera Barat", "MISI"),
        ],
    },
    {
        "kode": "UIKT",
        "nama_resmi": "GMAHK UIKT",
        "kawasan": "Tengah",
        "misi_list": [
            ("DK.JATENG", "Misi DK Jawa Tengah", "MISI"),
            ("DK.KALTENG", "Misi DK Kalimantan Tengah", "MISI"),
        ],
    },
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for udef in UNI_DEFS:
            # 1) Uni — idempotent by kode
            uni = db.query(Uni).filter(Uni.kode == udef["kode"]).first()
            if not uni:
                uni = Uni(kode=udef["kode"], nama_resmi=udef["nama_resmi"])
                db.add(uni)
                db.commit()
                db.refresh(uni)
                print(f"✓ Uni created: {uni.nama_resmi} — Kawasan {udef['kawasan']} (id={uni.id}, kode={uni.kode})")
            else:
                print(f"· Uni exists: {uni.nama_resmi} (id={uni.id})")

            # 2) Misi per Uni — idempotent by kode
            for mkode, mnama, mjenis in udef["misi_list"]:
                m = db.query(MisiKonferens).filter(MisiKonferens.kode == mkode).first()
                if not m:
                    m = MisiKonferens(
                        kode=mkode,
                        nama_resmi=mnama,
                        uni_id=uni.id,
                        jenis=mjenis,
                    )
                    db.add(m)
                    db.commit()
                    db.refresh(m)
                    print(f"  ✓ Misi created: {m.nama_resmi} (id={m.id}, kode={m.kode})")
                else:
                    print(f"  · Misi exists: {m.nama_resmi} (id={m.id})")

                # 3) PersentaseConfig per Misi (scope=MISI) — idempotent
                cfg = (
                    db.query(PersentaseConfig)
                    .filter(
                        PersentaseConfig.scope == "MISI",
                        PersentaseConfig.ref_id == m.id,
                    )
                    .first()
                )
                if not cfg:
                    cfg = PersentaseConfig(
                        scope="MISI",
                        ref_id=m.id,
                        pct_x_jemaat=0.0,       # 0% X tinggal di Jemaat → 100% X ke Misi (SDA tithe doctrine)
                        pct_pt_jemaat=0.5,      # default 50% PT ke Jemaat
                        pct_khusus_jemaat=0.0,  # KH locked
                    )
                    db.add(cfg)
                    db.commit()
                    print(f"    ✓ PersentaseConfig MISI/{mkode} created")
                else:
                    print(f"    · PersentaseConfig MISI/{mkode} exists")

            # 4) PersentaseConfig per Uni (scope=UNI) — idempotent
            cfg_u = (
                db.query(PersentaseConfig)
                .filter(
                    PersentaseConfig.scope == "UNI",
                    PersentaseConfig.ref_id == uni.id,
                )
                .first()
            )
            if not cfg_u:
                cfg_u = PersentaseConfig(
                    scope="UNI",
                    ref_id=uni.id,
                    pct_x_uni=0.0,        # default 0% (konservatif)
                    pct_pt_uni=0.0,       # default 0%
                    pct_khusus_uni=0.0,   # KH locked
                )
                db.add(cfg_u)
                db.commit()
                print(f"    ✓ PersentaseConfig UNI/{udef['kode']} created")
            else:
                print(f"    · PersentaseConfig UNI/{udef['kode']} exists")

        print("\n✓ Selesai. Total Uni sekarang:")
        for u in db.query(Uni).order_by(Uni.id).all():
            print(f"  - id={u.id}  kode={u.kode}  nama={u.nama_resmi}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
