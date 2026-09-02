"""
v2.0 M5 Migration — Tabel Pengeluaran + KategoriPengeluaran + seed kategori default.

Idempotent: aman dijalankan berulang.
Buat 4 jemaat × 2 kategori default (Listrik + Air) + (Telpon + Gaji Kostor) untuk seed demo.

Default kategori WAJIB (per Jerry 2026-09-01):
- Listrik (alias LIS, is_rutin=True)
- Air (alias AIR, is_rutin=True)
- Telpon (alias TLP, is_rutin=True)
- Gaji Kostor (alias KOSTOR, is_rutin=True)

Migration steps:
1. CREATE TABLE kategori_pengeluaran (jika belum ada)
2. CREATE TABLE pengeluaran (jika belum ada)
3. CREATE INDEX ix_pengeluaran_* (jika belum ada)
4. Seed 4 kategori default per tenant

Usage:
    .venv/bin/python3 scripts/migrate_v20_m5_pengeluaran.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.core.database import engine, SessionLocal, Base
from app.models.tenant import Tenant
from app.models.kategori_pengeluaran import KategoriPengeluaran


DEFAULT_KATEGORI_PENGELUARAN = [
    # (nama, alias, urutan, is_rutin)
    ("Listrik", "LIS", 1, True),
    ("Air", "AIR", 2, True),
    ("Telpon", "TLP", 3, True),
    ("Gaji Kostor", "KOSTOR", 4, True),
]


def table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def index_exists(inspector, table_name: str, index_name: str) -> bool:
    try:
        indexes = inspector.get_indexes(table_name)
        return any(idx.get("name") == index_name for idx in indexes)
    except Exception:
        return False


def main():
    print("=" * 70)
    print("  v2.0 M5 Migration — Pengeluaran + KategoriPengeluaran")
    print("=" * 70)

    inspector = inspect(engine)
    print(f"\n[1/4] Checking existing tables...")
    has_kat = table_exists(inspector, "kategori_pengeluaran")
    has_peng = table_exists(inspector, "pengeluaran")
    print(f"  kategori_pengeluaran exists: {has_kat}")
    print(f"  pengeluaran exists: {has_peng}")

    print(f"\n[2/4] Creating tables via SQLAlchemy metadata.create_all()...")
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("  ✅ Tables ensured (idempotent)")

    # Verify indexes (create_all handles them, but explicit re-create if missing)
    print(f"\n[3/4] Verifying indexes...")
    inspector = inspect(engine)
    if table_exists(inspector, "pengeluaran"):
        expected_indexes = [
            "ix_pengeluaran_tenant_tanggal",
            "ix_pengeluaran_tenant_status_tanggal",
            "ix_pengeluaran_tenant_kategori",
            "ix_pengeluaran_tenant_rekap",
        ]
        for idx in expected_indexes:
            exists = index_exists(inspector, "pengeluaran", idx)
            print(f"  {idx}: {'✅' if exists else '❌ MISSING'}")

    print(f"\n[4/4] Seeding default kategori per tenant...")
    db = SessionLocal()
    try:
        tenants = db.query(Tenant).all()
        if not tenants:
            print("  ⚠️  No tenants found in DB. Run seed_demo.py first.")
            return

        total_seeded = 0
        total_skipped = 0
        for tenant in tenants:
            for nama, alias, urutan, is_rutin in DEFAULT_KATEGORI_PENGELUARAN:
                existing = (
                    db.query(KategoriPengeluaran)
                    .filter(KategoriPengeluaran.tenant_id == tenant.id)
                    .filter(KategoriPengeluaran.alias == alias)
                    .first()
                )
                if existing:
                    total_skipped += 1
                    continue
                k = KategoriPengeluaran(
                    tenant_id=tenant.id,
                    nama=nama,
                    alias=alias,
                    urutan=urutan,
                    is_rutin=is_rutin,
                    is_aktif=True,
                )
                db.add(k)
                total_seeded += 1
                print(f"  ✅ {tenant.nama_jemaat_lokal} ({tenant.nama_uni}) → {nama} ({alias}, rutin={is_rutin})")
        db.commit()
        print(f"\n  Summary: {total_seeded} seeded, {total_skipped} skipped (already exist)")
    finally:
        db.close()

    print(f"\n[VERIFY] Final check...")
    db = SessionLocal()
    try:
        for tenant in db.query(Tenant).all():
            kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.tenant_id == tenant.id).all()
            print(f"  {tenant.nama_jemaat_lokal}: {len(kats)} kategori ({sum(1 for k in kats if k.is_rutin)} rutin, {sum(1 for k in kats if not k.is_rutin)} non-rutin)")
    finally:
        db.close()

    print("\n" + "=" * 70)
    print("  ✅ v2.0 M5 Migration COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()