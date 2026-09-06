"""
FASE 5 Sprint 4 — Unit tests for app/utils/nomor_kuitansi.py.

Pure-logic functions — no DB, no FastAPI. Covers:
- bulan_ke_romawi: month → Roman numeral (1=I ... 12=XII).
- generate_nomor_kuitansi: GMAHK receipt number format.
- generate_id_rekap_mingguan: weekly recap ID.
"""

from datetime import datetime

import pytest

from app.utils.nomor_kuitansi import (
    bulan_ke_romawi,
    generate_id_rekap_mingguan,
    generate_nomor_kuitansi,
)


class TestBulanKeRomawi:
    def test_januari(self) -> None:
        assert bulan_ke_romawi(1) == "I"

    def test_desember(self) -> None:
        assert bulan_ke_romawi(12) == "XII"

    def test_april(self) -> None:
        assert bulan_ke_romawi(4) == "IV"

    def test_september(self) -> None:
        assert bulan_ke_romawi(9) == "IX"

    def test_below_range(self) -> None:
        with pytest.raises(ValueError, match="Bulan harus 1-12"):
            bulan_ke_romawi(0)

    def test_above_range(self) -> None:
        with pytest.raises(ValueError, match="Bulan harus 1-12"):
            bulan_ke_romawi(13)


class TestGenerateNomorKuitansi:
    def test_basic(self) -> None:
        tgl = datetime(2026, 1, 15)
        nomor = generate_nomor_kuitansi(urutan=1, initial_jemaat="NT", tanggal=tgl)
        assert nomor == "001/NT/I/26"

    def test_urutan_padded_3_digits(self) -> None:
        tgl = datetime(2026, 12, 31)
        nomor = generate_nomor_kuitansi(urutan=42, initial_jemaat="NT", tanggal=tgl)
        assert nomor == "042/NT/XII/26"

    def test_initial_uppercased(self) -> None:
        tgl = datetime(2026, 6, 1)
        nomor = generate_nomor_kuitansi(urutan=1, initial_jemaat="nt", tanggal=tgl)
        assert nomor == "001/NT/VI/26"

    def test_initial_max_4_chars(self) -> None:
        tgl = datetime(2026, 6, 1)
        # 6 chars truncated to 4
        nomor = generate_nomor_kuitansi(urutan=1, initial_jemaat="ABCDEF", tanggal=tgl)
        assert "ABCD" in nomor

    def test_year_2_digits(self) -> None:
        tgl = datetime(2099, 1, 1)
        nomor = generate_nomor_kuitansi(urutan=1, initial_jemaat="NT", tanggal=tgl)
        assert nomor.endswith("/99")

    def test_urutan_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="urutan harus"):
            generate_nomor_kuitansi(urutan=0, initial_jemaat="NT")

    def test_urutan_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="urutan harus"):
            generate_nomor_kuitansi(urutan=-1, initial_jemaat="NT")

    def test_empty_initial_rejected(self) -> None:
        with pytest.raises(ValueError, match="initial_jemaat"):
            generate_nomor_kuitansi(urutan=1, initial_jemaat="")


class TestGenerateIdRekapMingguan:
    def test_format(self) -> None:
        # 2026-08-22 is a Saturday (ISO week 34)
        tgl = datetime(2026, 8, 22)
        rid = generate_id_rekap_mingguan(tgl)
        assert rid == "RK-20260822-2026W34"

    def test_format_first_week(self) -> None:
        # 2026-01-01 is a Thursday, ISO week 1
        tgl = datetime(2026, 1, 1)
        rid = generate_id_rekap_mingguan(tgl)
        assert rid.startswith("RK-20260101-2026W")
        assert "W01" in rid
