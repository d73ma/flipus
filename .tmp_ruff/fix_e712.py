#!/usr/bin/env python3
"""Convert SQLAlchemy filter `Column == False/True` to `Column.is_(False/True)`.

These are all inside `.filter(...)`, `.filter_by(...)`, or `filters.append(...)`
clauses that build SQLAlchemy query expressions. The `==` operator works but
emits a non-idiomatic SQL `=` comparison; `.is_(False)` / `.is_(True)` is the
SQLAlchemy-recommended idiom and is lint-clean.

NOTE: This is the OPPOSITE of what ruff's --fix --unsafe-fixes does (which
would change `==` to Python `is`, breaking SQL semantics). We use the
SQLAlchemy method explicitly.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/Users/jerrymauri/Flipus")

# (file, line_no, lhs, rhs) — exactly the lines ruff flagged
EDITS: list[tuple[str, int, str, str]] = [
    # app/api/v1/kuitansi.py
    ("app/api/v1/kuitansi.py", 177, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/kuitansi.py", 401, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/kuitansi.py", 539, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    # app/api/v1/laporan_gabungan.py
    ("app/api/v1/laporan_gabungan.py", 144, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/laporan_gabungan.py", 156, "Pengeluaran.is_purged == False", "Pengeluaran.is_purged.is_(False)"),
    ("app/api/v1/laporan_gabungan.py", 262, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/laporan_gabungan.py", 271, "Pengeluaran.is_purged == False", "Pengeluaran.is_purged.is_(False)"),
    ("app/api/v1/laporan_gabungan.py", 384, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/laporan_gabungan.py", 393, "Pengeluaran.is_purged == False", "Pengeluaran.is_purged.is_(False)"),
    # app/api/v1/pengeluaran_ocr.py
    ("app/api/v1/pengeluaran_ocr.py", 126, "KategoriPengeluaran.is_aktif == True", "KategoriPengeluaran.is_aktif.is_(True)"),
    # app/api/v1/quick_input.py
    ("app/api/v1/quick_input.py", 111, "KategoriPemasukan.is_aktif == True", "KategoriPemasukan.is_aktif.is_(True)"),
    ("app/api/v1/quick_input.py", 173, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/quick_input.py", 232, "Tenant.is_active == True", "Tenant.is_active.is_(True)"),
    ("app/api/v1/quick_input.py", 391, "KategoriPemasukan.is_aktif == True", "KategoriPemasukan.is_aktif.is_(True)"),
    # app/api/v1/reports.py
    ("app/api/v1/reports.py", 116, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/reports.py", 213, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    ("app/api/v1/reports.py", 320, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    # app/api/v1/sync.py
    ("app/api/v1/sync.py", 58, "Kuitansi.is_purged == False", "Kuitansi.is_purged.is_(False)"),
    # app/api/v1/wa_input.py
    ("app/api/v1/wa_input.py", 475, "User.is_active == True", "User.is_active.is_(True)"),
    ("app/api/v1/wa_input.py", 768, "Kuitansi.is_finalized == False", "Kuitansi.is_finalized.is_(False)"),
    ("app/api/v1/wa_input.py", 898, "Kuitansi.is_finalized == False", "Kuitansi.is_finalized.is_(False)"),
    ("app/api/v1/wa_input.py", 912, "Kuitansi.is_finalized == True", "Kuitansi.is_finalized.is_(True)"),
    ("app/api/v1/wa_input.py", 959, "Kuitansi.is_finalized == False", "Kuitansi.is_finalized.is_(False)"),
    ("app/api/v1/wa_input.py", 1021, "Kuitansi.is_finalized == False", "Kuitansi.is_finalized.is_(False)"),
    ("app/api/v1/wa_input.py", 1054, "Kuitansi.is_finalized == True", "Kuitansi.is_finalized.is_(True)"),
    # scripts/
    ("scripts/backfill_t110_tanggal_staging.py", 34, "Tenant.is_active == True", "Tenant.is_active.is_(True)"),
    ("scripts/backfill_t110_tanggal_staging.py", 42, "Kuitansi.is_finalized == True", "Kuitansi.is_finalized.is_(True)"),
    ("scripts/inspect_staging_old.py", 31, "Kuitansi.is_finalized == True", "Kuitansi.is_finalized.is_(True)"),
]

# Group edits by file for single read/write per file
by_file: dict[str, list[tuple[int, str, str]]] = {}
for f, ln, lhs, rhs in EDITS:
    by_file.setdefault(f, []).append((ln, lhs, rhs))

total = 0
for rel, edits in by_file.items():
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for ln, lhs, rhs in sorted(edits, key=lambda e: -e[0]):
        idx = ln - 1
        old = lines[idx]
        if lhs not in old:
            print(f"!! MISS in {rel}:{ln}  expected {lhs!r}")
            print(f"   actual: {old!r}")
            raise SystemExit(1)
        new = old.replace(lhs, rhs)
        lines[idx] = new
        total += 1
        print(f"   patched {rel}:{ln}: {lhs} -> {rhs}")
    p.write_text("".join(lines), encoding="utf-8")

print(f"\nE712: rewrote {total} SQLAlchemy `==` to `.is_()`.")
