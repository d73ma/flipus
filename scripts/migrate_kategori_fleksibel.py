"""
v2.0 M3 — Schema migration + seed default kategori.

Idempotent. Bisa dijalankan berulang tanpa efek samping.

Cara kerja:
1. CREATE TABLE kategori_pemasukan + kuitansi_kategori (kalau belum ada)
2. Seed default per tenant aktif: X (alias 'X') + PT (alias 'PT')
3. KH TIDAK di-seed — akan auto-create saat Bendahara pertama ketik "Khusus"
4. Migration data existing: baca Kuitansi.perpuluhan_x_angka/pt_angka/khusus_angka
   → INSERT ke kuitansi_kategori dengan kategori_id yang sesuai

Usage:
    .venv/bin/python3 scripts/migrate_kategori_fleksibel.py

Pre-condition:
- Backend FLIPUS sudah pernah jalan minimal 1× (tabel tenants sudah ada)
- v2.0 model sudah di-import di app.models.__init__.py
"""
import os
import sys
from datetime import datetime

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import Base, engine, SessionLocal
from app.models import Tenant, Kuitansi, KategoriPemasukan, KuitansiKategori


# Kategori default: hanya X + PT (KH auto-create nanti)
DEFAULT_KATEGORI = [
    {"nama": "Perpuluhan", "alias": "X", "urutan": 1, "is_rutin": True},
    {"nama": "Persembahan Terpadu", "alias": "PT", "urutan": 2, "is_rutin": True},
]


def create_tables():
    """CREATE TABLE kalau belum ada."""
    print("[1/4] Creating tables (kalau belum ada)...")
    Base.metadata.create_all(bind=engine, tables=[
        KategoriPemasukan.__table__,
        KuitansiKategori.__table__,
    ])
    print("  -> OK")


def seed_default_kategori():
    """Seed X + PT per tenant aktif (jemaat lokal). KH tidak di-seed."""
    print("\n[2/4] Seeding default kategori (X + PT) per tenant...")
    db = SessionLocal()
    try:
        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        if not tenants:
            print("  -> Tidak ada tenant aktif, skip")
            return

        added = 0
        skipped = 0
        for t in tenants:
            for spec in DEFAULT_KATEGORI:
                existing = (
                    db.query(KategoriPemasukan)
                    .filter(
                        KategoriPemasukan.tenant_id == t.id,
                        KategoriPemasukan.alias == spec["alias"],
                    )
                    .first()
                )
                if existing:
                    skipped += 1
                    continue
                k = KategoriPemasukan(
                    tenant_id=t.id,
                    nama=spec["nama"],
                    alias=spec["alias"],
                    urutan=spec["urutan"],
                    is_rutin=spec["is_rutin"],
                    is_aktif=True,
                )
                db.add(k)
                added += 1
        db.commit()
        print(f"  -> Added: {added}, Already exist: {skipped}, Tenants: {len(tenants)}")
    finally:
        db.close()


def migrate_existing_kuitansi():
    """
    Baca Kuitansi existing, migrasi ke kuitansi_kategori.

    Asumsi: sudah ada KategoriPemasukan dengan alias 'X', 'PT', 'KHUS'
    (untuk KH, auto-create 'Persembahan Khusus' kalau belum ada).
    """
    print("\n[3/4] Migrating existing Kuitansi to kuitansi_kategori...")
    db = SessionLocal()
    try:
        # Ensure KHUS kategori exists (kalau ada Kuitansi existing dengan khusus_angka > 0)
        khus_per_tenant = {}
        for t in db.query(Tenant).filter(Tenant.is_active == True).all():
            khus = (
                db.query(KategoriPemasukan)
                .filter(
                    KategoriPemasukan.tenant_id == t.id,
                    KategoriPemasukan.alias == "KHUS",
                )
                .first()
            )
            if not khus:
                khus = KategoriPemasukan(
                    tenant_id=t.id,
                    nama="Persembahan Khusus",
                    alias="KHUS",
                    urutan=3,
                    is_rutin=False,  # KH tidak default, is_rutin=False
                    is_aktif=True,
                )
                db.add(khus)
                db.flush()
            khus_per_tenant[t.id] = khus.id

        db.commit()

        # Map kategori_id per tenant (X, PT, KHUS)
        kat_map = {}  # (tenant_id, alias) -> kategori_id
        for k in db.query(KategoriPemasukan).filter(KategoriPemasukan.is_aktif == True).all():
            kat_map[(k.tenant_id, k.alias)] = k.id

        # Baca Kuitansi existing
        kuitansi_list = db.query(Kuitansi).all()
        if not kuitansi_list:
            print("  -> Tidak ada Kuitansi, skip")
            return

        added = 0
        skipped = 0
        for k in kuitansi_list:
            # Cek apakah sudah pernah di-migrasi (avoid duplicate)
            existing_pivot = db.query(KuitansiKategori).filter(KuitansiKategori.kuitansi_id == k.id).first()
            if existing_pivot:
                skipped += 1
                continue

            tenant_id = k.tenant_id
            items = [
                (k.perpuluhan_x_angka, "X"),
                (k.pt_angka, "PT"),
                (k.khusus_angka, "KHUS"),
            ]
            for nominal, alias in items:
                if nominal and nominal > 0:
                    kat_id = kat_map.get((tenant_id, alias))
                    if not kat_id:
                        print(f"  -> WARN: Kuitansi #{k.id} tenant {tenant_id} tidak ada kategori {alias}, skip")
                        continue
                    pivot = KuitansiKategori(
                        kuitansi_id=k.id,
                        kategori_id=kat_id,
                        nominal=nominal,
                    )
                    db.add(pivot)
                    added += 1
        db.commit()
        print(f"  -> Pivot rows added: {added}, Already migrated: {skipped}")
    finally:
        db.close()


def verify():
    """Verify hasil migrasi."""
    print("\n[4/4] Verifying...")
    db = SessionLocal()
    try:
        total_kat = db.query(KategoriPemasukan).count()
        total_pivot = db.query(KuitansiKategori).count()
        total_kuitansi = db.query(Kuitansi).count()

        print(f"  -> Total KategoriPemasukan: {total_kat}")
        print(f"  -> Total KuitansiKategori (pivot): {total_pivot}")
        print(f"  -> Total Kuitansi: {total_kuitansi}")

        # Sample: tampilkan 5 kategori pertama
        print("\n  Sample 5 KategoriPemasukan:")
        for k in db.query(KategoriPemasukan).limit(5).all():
            print(f"    id={k.id} tenant={k.tenant_id} nama={k.nama!r} alias={k.alias!r} rutin={k.is_rutin}")

        # Sample: tampilkan 5 pivot rows
        print("\n  Sample 5 KuitansiKategori:")
        for p in db.query(KuitansiKategori).limit(5).all():
            print(f"    id={p.id} kuitansi_id={p.kuitansi_id} kategori_id={p.kategori_id} nominal={p.nominal:,}")
    finally:
        db.close()


def main():
    print("=" * 60)
    print("  v2.0 M3 — Migration: Schema + Seed + Migrate Existing Data")
    print("=" * 60)

    # Pre-check
    db = SessionLocal()
    try:
        tenant_count = db.query(Tenant).count()
        print(f"\nPre-check: {tenant_count} tenants di DB")
        if tenant_count == 0:
            print("\nERROR: Tidak ada tenant. Jalankan seed_demo.py dulu.")
            sys.exit(1)
    finally:
        db.close()

    create_tables()
    seed_default_kategori()
    migrate_existing_kuitansi()
    verify()

    print("\n" + "=" * 60)
    print("  Selesai ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()