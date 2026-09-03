"""
S4-F.R4 — Unit tests untuk app.services.financial_calculator.

Coverage target: 100% (21 stmts).

Menguji distribusi persembahan sesuai konfigurasi persentase GMAHK:
- X (Perpuluhan) -> 100% ke Kantor Misi (default pct_x_jemaat=1.0)
- PT (Persembahan Terpadu) -> 50% Misi + 50% Kas Jemaat (default pct_pt_jemaat=0.5)
- Khusus -> 50% Misi + 50% Kas Jemaat (default pct_khusus_jemaat=0.5)
- Layer 2: Misi -> Uni (potong dari porsi_misi, default pct_*_uni=0.0)

Aturan Jerry (audit FASE 3-S4): kode ini adalah financial core — Wajib 100% covered.
"""

import pytest

from app.services.financial_calculator import calculate_distribution


class TestCalculateDistributionBasic:
    """Distribusi dasar (Layer 1 only, default config)."""

    def test_x_only_default_pct(self):
        """X 100rb → 100rb ke Misi, 0 di Jemaat (pct_x_jemaat=1.0)."""
        result = calculate_distribution(perpuluhan_x=100_000, pt=0)
        assert result["total"] == 100_000
        assert result["porsi_kantor_misi"] == 100_000
        assert result["porsi_kas_jemaat"] == 0
        assert result["porsi_khusus_jemaat"] == 0
        assert result["porsi_x_misi_net"] == 100_000

    def test_pt_only_default_pct(self):
        """PT 100rb 50rb Misi + 50rb Jemaat."""
        result = calculate_distribution(perpuluhan_x=0, pt=100_000)
        assert result["total"] == 100_000
        assert result["porsi_kantor_misi"] == 50_000
        assert result["porsi_kas_jemaat"] == 50_000
        assert result["porsi_pt_misi_net"] == 50_000

    def test_khusus_only_default_pct(self):
        """Khusus 100rb → 50rb Misi + 50rb Jemaat."""
        result = calculate_distribution(perpuluhan_x=0, pt=0, khusus=100_000)
        assert result["total"] == 100_000
        assert result["porsi_kantor_misi"] == 50_000
        assert result["porsi_kas_jemaat"] == 50_000
        assert result["porsi_khusus_misi"] == 50_000
        assert result["porsi_khusus_jemaat"] == 50_000

    def test_combined_x_pt_khusus(self):
        """Gabungan: X 100rb + PT 50rb + Khusus 25rb = 175rb."""
        result = calculate_distribution(perpuluhan_x=100_000, pt=50_000, khusus=25_000)
        assert result["total"] == 175_000
        # X: 100rb ke Misi
        # PT: 25rb Misi + 25rb Jemaat
        # Khusus: 12.5rb Misi + 12.5rb Jemaat → int conversion = 12rb Misi, 13rb Jemaat
        assert result["porsi_kantor_misi"] == 100_000 + 25_000 + 12_500
        assert result["porsi_kas_jemaat"] == 0 + 25_000 + 12_500

    def test_khusus_default_zero(self):
        """Khusus default = 0 kalau tidak di-passing."""
        result = calculate_distribution(perpuluhan_x=50_000, pt=10_000)
        assert result["total"] == 60_000
        assert result["porsi_khusus_misi"] == 0
        assert result["porsi_khusus_jemaat"] == 0
        assert result["porsi_khusus_misi_net"] == 0
        assert result["porsi_khusus_uni"] == 0


class TestCalculateDistributionCustomPct:
    """Override percentage config (untuk testing config flexibility)."""

    def test_x_custom_pct_50(self):
        """X dengan pct_x_jemaat=0.5 → 50% Misi + 50% Jemaat."""
        result = calculate_distribution(perpuluhan_x=100_000, pt=0, pct_x_jemaat=0.5)
        assert result["porsi_kantor_misi"] == 50_000
        assert result["porsi_kas_jemaat"] == 50_000

    def test_pt_custom_pct_100(self):
        """PT dengan pct_pt_jemaat=1.0 → 100% ke Misi (kas jemaat 0)."""
        result = calculate_distribution(perpuluhan_x=0, pt=100_000, pct_pt_jemaat=1.0)
        assert result["porsi_kantor_misi"] == 100_000
        assert result["porsi_kas_jemaat"] == 0

    def test_khusus_custom_pct_25(self):
        """Khusus dengan pct_khusus_jemaat=0.25 → 25% Misi + 75% Jemaat."""
        result = calculate_distribution(perpuluhan_x=0, pt=0, khusus=100_000, pct_khusus_jemaat=0.25)
        assert result["porsi_khusus_misi"] == 25_000
        assert result["porsi_khusus_jemaat"] == 75_000


class TestCalculateDistributionLayer2:
    """Layer 2: Misi -> Uni (potongan untuk Uni)."""

    def test_x_uni_pct_zero_default(self):
        """Default: pct_x_uni=0 → tidak ada potongan ke Uni."""
        result = calculate_distribution(perpuluhan_x=100_000, pt=0)
        assert result["porsi_x_uni"] == 0
        assert result["porsi_x_misi_net"] == 100_000
        assert result["total_porsi_uni"] == 0

    def test_x_uni_pct_10(self):
        """pct_x_uni=0.1 → Uni dapat 10% dari porsi_misi."""
        result = calculate_distribution(perpuluhan_x=100_000, pt=0, pct_x_uni=0.1)
        assert result["porsi_x_uni"] == 10_000  # 100rb * 1.0 * 0.1
        assert result["porsi_x_misi_net"] == 90_000
        assert result["total_porsi_uni"] == 10_000

    def test_pt_uni_pct_50(self):
        """pct_pt_uni=0.5 → Uni dapat 50% dari porsi_pt_misi."""
        result = calculate_distribution(perpuluhan_x=0, pt=100_000, pct_pt_uni=0.5)
        assert result["porsi_pt_uni"] == 25_000  # 100rb * 0.5 * 0.5
        assert result["porsi_pt_misi_net"] == 25_000

    def test_khusus_uni_pct_20(self):
        """pct_khusus_uni=0.2 → Uni dapat 20% dari porsi_khusus_misi."""
        result = calculate_distribution(perpuluhan_x=0, pt=0, khusus=50_000, pct_khusus_uni=0.2)
        assert result["porsi_khusus_uni"] == 5_000  # 50rb * 0.5 * 0.2
        assert result["porsi_khusus_misi_net"] == 20_000

    def test_all_uni_pct_combined(self):
        """Gabungan Layer 1 + Layer 2: Uni potong X, PT, Khusus."""
        result = calculate_distribution(
            perpuluhan_x=100_000,
            pt=100_000,
            khusus=100_000,
            pct_x_jemaat=1.0,
            pct_pt_jemaat=0.5,
            pct_khusus_jemaat=0.5,
            pct_x_uni=0.1,
            pct_pt_uni=0.1,
            pct_khusus_uni=0.1,
        )
        # X: 100rb Misi, 0 Jemaat; Uni 10rb; net Misi 90rb
        # PT: 50rb Misi, 50rb Jemaat; Uni 5rb; net Misi 45rb
        # Khusus: 50rb Misi, 50rb Jemaat; Uni 5rb; net Misi 45rb
        assert result["porsi_x_uni"] == 10_000
        assert result["porsi_pt_uni"] == 5_000
        assert result["porsi_khusus_uni"] == 5_000
        assert result["total_porsi_uni"] == 20_000
        assert result["porsi_x_misi_net"] == 90_000
        assert result["porsi_pt_misi_net"] == 45_000
        assert result["porsi_khusus_misi_net"] == 45_000
        assert result["porsi_kantor_misi"] == 200_000  # total ke Misi (sebelum dipotong Uni)
        assert result["porsi_kas_jemaat"] == 100_000  # 0 + 50rb + 50rb
        assert result["total"] == 300_000


class TestCalculateDistributionValidation:
    """Validasi input negatif → ValueError."""

    def test_x_negative_raises(self):
        with pytest.raises(ValueError, match="tidak boleh negatif"):
            calculate_distribution(perpuluhan_x=-100, pt=0)

    def test_pt_negative_raises(self):
        with pytest.raises(ValueError, match="tidak boleh negatif"):
            calculate_distribution(perpuluhan_x=0, pt=-1)

    def test_khusus_negative_raises(self):
        with pytest.raises(ValueError, match="tidak boleh negatif"):
            calculate_distribution(perpuluhan_x=0, pt=0, khusus=-50_000)


class TestCalculateDistributionZeroAll:
    """Boundary: semua 0 → result semua 0."""

    def test_all_zero(self):
        result = calculate_distribution(perpuluhan_x=0, pt=0, khusus=0)
        assert result["total"] == 0
        assert result["porsi_kantor_misi"] == 0
        assert result["porsi_kas_jemaat"] == 0
        assert result["porsi_x_misi_net"] == 0
        assert result["porsi_pt_misi_net"] == 0
        assert result["porsi_khusus_misi_net"] == 0
        assert result["total_porsi_uni"] == 0
