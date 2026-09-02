"""
FLIPUS v1.1 — Test PDF generator.

Jalankan di Mac setelah backend running:
    /Users/jerrymauri/Flipus/.venv/bin/python3 -m storage.scripts.test_pdf

Test:
1. Generate dummy Kuitansi list
2. Generate PDF
3. Save ke storage/temp/test_output.pdf
4. Print ukuran file

Atau test langsung via API:
    curl -X POST http://localhost:8000/api/v1/reports/blast-weekly \
        -H "Authorization: Bearer <TOKEN>" \
        -H "Content-Type: application/json" \
        -d '{"id_rekap_mingguan": "FLIPUS-2026-DEMO-001"}'
"""

import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())

from datetime import datetime
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.services.pdf_generator import generate_mingguan_pdf


def make_dummy_kuitansi():
    """Generate 5 dummy Kuitansi objects."""
    items = []
    for i in range(1, 6):
        k = Kuitansi(
            id=i,
            tenant_id=1,
            id_rekap_mingguan="FLIPUS-2026-DEMO-001",
            nomor_kuitansi=f"001/NT/I/27-{i:02d}",
            tanggal_sabat="2026-08-22",
            perpuluhan_x_angka=500_000 * i,
            pt_angka=200_000 * i,
            khusus_angka=100_000 if i % 2 == 0 else 0,
            total_pemberian_angka=(500_000 + 200_000) * i + (100_000 if i % 2 == 0 else 0),
            total_pemberian_huruf="",
            porsi_kantor_misi=(500_000 * i) + (200_000 * i * 0.5),
            porsi_kas_jemaat=(200_000 * i * 0.5),
            porsi_khusus_misi=50_000 if i % 2 == 0 else 0,
            porsi_khusus_jemaat=50_000 if i % 2 == 0 else 0,
        )
        items.append(k)
    return items


def make_dummy_tenant():
    return Tenant(
        id=1,
        tenant_signature="dummy",
        nama_uni="GMAHK Uni Konferens Indonesia Kawasan Timur",
        nama_kantor_misi="Daerah Konferens Minahasa",
        nama_jemaat_lokal="Jemaat Nataan",
        initial_jemaat="NT",
        nama_pendeta="Steven Purba, S.Th",
        nama_ketua_keuangan="Bpk. Jefry Mantik",
        nama_bendahara="Ibu Olha Wenas",
        misi_konferens_id=1,
    )


def main():
    print("=== TEST PDF Generator ===")

    kuitansi_list = make_dummy_kuitansi()
    tenant = make_dummy_tenant()

    # Save ke temp folder
    output_dir = os.path.join(os.getcwd(), "storage", "temp")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "test_laporan_mingguan.pdf")

    pdf_bytes = generate_mingguan_pdf(
        kuitansi_list=kuitansi_list,
        tenant=tenant,
        id_rekap_mingguan="FLIPUS-2026-DEMO-001",
        tanggal_sabat_iso="2026-08-22",
        output_path=output_path,
    )

    print(f"\nPDF generated successfully!")
    print(f"  Path: {output_path}")
    print(f"  Size: {len(pdf_bytes):,} bytes ({len(pdf_bytes)/1024:.1f} KB)")
    print(f"  Kuitansi: {len(kuitansi_list)}")
    print(f"  Total: Rp {sum(k.perpuluhan_x_angka + k.pt_angka + k.khusus_angka for k in kuitansi_list):,}")
    print(f"\nBuka file di: {output_path}")
    print(f"Atau: open {output_path}")


if __name__ == "__main__":
    main()
