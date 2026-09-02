"""
v1.5-C — Migration: tambah tabel blast_jobs.

Idempotent. Aman jalan berulang.

Cara pakai:
    cd /Users/jerrymauri/Flipus
    /Users/jerrymauri/Flipus/.venv/bin/python3 scripts/migrate_v15_blast.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

from sqlalchemy import inspect
from app.core.database import engine, Base
# Import ALL models agar Base.metadata.create_all() bisa create blast_jobs
from app.models.blast_job import BlastJob  # noqa: F401


def main():
    print("=" * 60)
    print("v1.5-C Migration: blast_jobs (idempotency table)")
    print("=" * 60)

    print("\n→ CREATE TABLE blast_jobs:")
    Base.metadata.create_all(bind=engine, tables=[BlastJob.__table__])
    inspector = inspect(engine)
    if "blast_jobs" in inspector.get_table_names():
        print("  ✓ Tabel blast_jobs ada")
    else:
        print("  ✗ Tabel blast_jobs gagal dibuat")
        return

    print("\n" + "=" * 60)
    print("✓ v1.5-C Migration selesai")
    print("=" * 60)


if __name__ == "__main__":
    main()