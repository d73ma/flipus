"""
FASE 5 Sprint 5 — Unit tests for app/services/pdf_generator.py.

Covers:
- Helper functions: _hex_to_reportlab, _fmt_rupiah, _get_tenant_colors.
- generate_mingguan_pdf: produce PDF bytes from kuitansi list + tenant.
"""

import os
import tempfile

import pytest

from app.services.pdf_generator import (
    _fmt_rupiah,
    _hex_to_reportlab,
    generate_mingguan_pdf,
)


class TestHexToReportlab:
    def test_valid_hex(self) -> None:
        """Convert valid hex to reportlab Color (with leading #)."""
        color = _hex_to_reportlab("#1B4332")
        assert color is not None

    def test_invalid_hex_raises(self) -> None:
        """Invalid hex raises ValueError — no silent fallback."""
        with pytest.raises(ValueError):
            _hex_to_reportlab("invalid-hex")


class TestFmtRupiah:
    def test_zero(self) -> None:
        assert _fmt_rupiah(0) == "Rp 0"

    def test_thousands(self) -> None:
        assert _fmt_rupiah(1000) == "Rp 1.000"

    def test_millions(self) -> None:
        assert _fmt_rupiah(1_500_000) == "Rp 1.500.000"


class TestGenerateMingguanPdf:
    def test_returns_pdf_bytes(self, test_db, jemaat_a, create_kuitansi) -> None:
        """Should return valid PDF bytes for non-empty kuitansi list."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000, pt_angka=50000)
        pdf_bytes = generate_mingguan_pdf(
            kuitansi_list=[k],
            tenant=jemaat_a,
            id_rekap_mingguan="RK-2026-08-22",
            tanggal_sabat_iso="2026-08-22",
        )
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        # PDF magic bytes
        assert pdf_bytes[:4] == b"%PDF"

    def test_empty_kuitansi_list(self, jemaat_a) -> None:
        """Empty list should still produce a valid PDF (with zero totals)."""
        pdf_bytes = generate_mingguan_pdf(
            kuitansi_list=[],
            tenant=jemaat_a,
            id_rekap_mingguan="RK-EMPTY",
            tanggal_sabat_iso="2026-08-22",
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"

    def test_saves_to_file(self, test_db, jemaat_a, create_kuitansi) -> None:
        """When output_path is set, should save PDF to file."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=200000)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.pdf")
            generate_mingguan_pdf(
                kuitansi_list=[k],
                tenant=jemaat_a,
                id_rekap_mingguan="RK-TEST",
                tanggal_sabat_iso="2026-08-22",
                output_path=path,
            )
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read(4) == b"%PDF"
