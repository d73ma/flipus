"""
FASE 5 Sprint 5 — Unit tests for app/services/pdf_gabungan.py.

Covers generate_gabungan_pdf: produce PDF combining Kuitansi + Pengeluaran.
"""

import os
import tempfile

from app.services.pdf_gabungan import generate_gabungan_pdf


class TestGenerateGabunganPdf:
    def test_returns_pdf_bytes(self, test_db, jemaat_a, create_kuitansi) -> None:
        """Should return valid PDF bytes with combined data."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000, pt_angka=50000)
        pdf_bytes = generate_gabungan_pdf(
            kuitansi_list=[k],
            pengeluaran_list=[],
            tenant=jemaat_a,
            id_rekap_mingguan="RK-2026-08-22",
            tanggal_sabat_iso="2026-08-22",
            kategori_map={},
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"

    def test_empty_lists(self, jemaat_a) -> None:
        """Empty kuitansi + empty pengeluaran should still produce a PDF."""
        pdf_bytes = generate_gabungan_pdf(
            kuitansi_list=[],
            pengeluaran_list=[],
            tenant=jemaat_a,
            id_rekap_mingguan="RK-EMPTY",
            tanggal_sabat_iso="2026-08-22",
            kategori_map={},
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"

    def test_saves_to_file(self, test_db, jemaat_a, create_kuitansi) -> None:
        """When output_path is set, saves to file."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=200000)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "gabungan.pdf")
            generate_gabungan_pdf(
                kuitansi_list=[k],
                pengeluaran_list=[],
                tenant=jemaat_a,
                id_rekap_mingguan="RK-TEST",
                tanggal_sabat_iso="2026-08-22",
                kategori_map={},
                output_path=path,
            )
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read(4) == b"%PDF"

    def test_with_pengeluaran(self, test_db, jemaat_a, create_kuitansi) -> None:
        """Should include pengeluaran rows in the PDF."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran
        from app.models.pengeluaran import Pengeluaran

        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000)
        # Create Pengeluaran row
        db = test_db()
        cat = KategoriPengeluaran(tenant_id=jemaat_a.id, nama="Listrik", alias="LST", is_aktif=True, urutan=1)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        peng = Pengeluaran(
            tenant_id=jemaat_a.id,
            nomor_pengeluaran="P-001",
            kategori_pengeluaran_id=cat.id,
            jumlah=50000,
            tanggal="2026-08-22",
            tanggal_sabat="2026-08-22",
            id_rekap_mingguan="RK-COMBO",
            status="approved",
        )
        db.add(peng)
        db.commit()
        db.refresh(peng)
        kat_map = {cat.id: cat}
        db.close()
        pdf_bytes = generate_gabungan_pdf(
            kuitansi_list=[k],
            pengeluaran_list=[peng],
            tenant=jemaat_a,
            id_rekap_mingguan="RK-COMBO",
            tanggal_sabat_iso="2026-08-22",
            kategori_map=kat_map,
        )
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 1000  # Should be larger with content
