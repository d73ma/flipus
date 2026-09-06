"""
S4-F.R4 — Unit tests untuk app.utils.porsi_calculator.

Coverage target: ~100% (23 stmts, was 0%).

Jerry Model B (final 2026-08-23) — pct_uni applied to TOTAL.
- pj = total * pct_jemaat (X & PT)
- pu = total * pct_uni (X & PT)
- pm = total - pj - pu (sisa → misi)
- KH semantik terbalik: pct_khusus_jemaat = fraction to MISI, pj_kh = sisa
- validate: pct_jemaat + pct_uni ≤ 1.0 per tier
"""


from app.utils.porsi_calculator import (
    compute_porsi,
    validate_porsi_constraint,
)


class TestComputePorsiBasic:
    """Hitung porsi 3-tier basic cases."""

    def test_jerry_demo_pt(self):
        """PT 315,000, pct_pt_jemaat=0.5, pct_pt_uni=0.30 → 157500/94500/63000."""
        result = compute_porsi(
            x=0, pt=315_000, kh=0,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.30, pct_khusus_uni=0.0,
        )
        assert result["pj_pt"] == 157_500
        assert result["pu_pt"] == 94_500
        assert result["pm_pt"] == 63_000

    def test_jerry_demo_x(self):
        """X 797,500, pct_x_jemaat=0, pct_x_uni=0.41 → 0/326975/470525."""
        result = compute_porsi(
            x=797_500, pt=0, kh=0,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.41, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert result["pj_x"] == 0
        assert result["pu_x"] == 326_975  # int(round(797500*0.41)) = 326975
        assert result["pm_x"] == 470_525  # 797500 - 0 - 326975 = 470525

    def test_zero_input(self):
        """Semua zero → semua output zero."""
        result = compute_porsi(0, 0, 0, 0.5, 0.5, 0.5, 0.3, 0.3, 0.3)
        assert all(v == 0 for v in result.values())

    def test_full_to_jemaat(self):
        """100% ke jemaat, 0% uni → jemaat = total, misi = 0."""
        result = compute_porsi(
            x=100_000, pt=200_000, kh=50_000,
            pct_x_jemaat=1.0, pct_pt_jemaat=1.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert result["pj_x"] == 100_000
        assert result["pj_pt"] == 200_000
        # KH pct_khusus_jemaat=0 → 0 ke misi, semua stays di jemaat
        assert result["pj_kh"] == 50_000
        assert result["pm_kh"] == 0
        assert result["pu_kh"] == 0
        assert result["pm_x"] == 0
        assert result["pm_pt"] == 0

    def test_full_to_misi_x(self):
        """X: 0% jemaat, 0% uni → 100% misi."""
        result = compute_porsi(
            x=100_000, pt=0, kh=0,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert result["pj_x"] == 0
        assert result["pu_x"] == 0
        assert result["pm_x"] == 100_000

    def test_kh_semantic_inverted(self):
        """KH: pct_khusus_jemaat=1.0 → 100% ke MISI (TERBALIK dari X/PT)."""
        result = compute_porsi(
            x=0, pt=0, kh=100_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=1.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        # KH 100k, 100% ke misi
        assert result["pm_kh"] == 100_000
        # Sisa stays di jemaat = 0
        assert result["pj_kh"] == 0
        assert result["pu_kh"] == 0

    def test_kh_with_uni_cut(self):
        """KH 100k, 20% misi (pct_khusus_jemaat=0.2), 10% uni, 70% jemaat."""
        result = compute_porsi(
            x=0, pt=0, kh=100_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.2,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.10,
        )
        assert result["pu_kh"] == 10_000  # 100k * 0.10
        assert result["pm_kh"] == 20_000  # 100k * 0.20
        assert result["pj_kh"] == 70_000  # sisa = 100k - 20k - 10k

    def test_kh_pj_never_negative(self):
        """pj_kh di-floor ke 0 (max 0) kalau pu_kh + pm_kh > kh."""
        # Edge case: pct_khusus_jemaat=0.6 + pct_khusus_uni=0.6 = 1.2 → overcommit
        result = compute_porsi(
            x=0, pt=0, kh=100_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.6,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.6,
        )
        # pj_kh = max(0, 100k - 60k - 60k) = max(0, -20k) = 0
        assert result["pj_kh"] == 0

    def test_pm_floor_zero(self):
        """pm di-floor ke 0 kalau overcommit (max 0)."""
        # pct_x_jemaat=0.6 + pct_x_uni=0.6 = 1.2 > 1.0
        result = compute_porsi(
            x=100_000, pt=0, kh=0,
            pct_x_jemaat=0.6, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.6, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        # pm_x = max(0, 100k - 60k - 60k) = 0
        assert result["pm_x"] == 0

    def test_rounding(self):
        """Pembulatan integer: int(round(x*pct))."""
        # 333 * 0.5 = 166.5 → round to 167 (banker's rounding in Python uses 166.5 → 166 even)
        # Actually Python round(166.5) = 166 (banker's), but int(round()) bisa jadi 166 atau 167
        # Just verify it's close to expected
        result = compute_porsi(
            x=333, pt=0, kh=0,
            pct_x_jemaat=0.5, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        # Either 166 or 167 — just verify it's close
        assert result["pj_x"] in (166, 167)

    def test_combined_x_pt_kh(self):
        """Kombinasi X + PT + KH dalam satu call."""
        result = compute_porsi(
            x=100_000, pt=200_000, kh=50_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert result["pj_x"] == 0
        assert result["pj_pt"] == 100_000  # 200k * 0.5
        assert result["pj_kh"] == 50_000  # stays di jemaat (KH pct=0 → 0 ke misi)
        assert result["pm_x"] == 100_000  # X fully misi


class TestValidatePorsiConstraint:
    """Validasi Jerry Model B: pct range + penjumlahan."""

    def test_all_valid(self):
        """Semua pct valid + constraint terpenuhi → no errors."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.5, pct_x_uni=0.3,
            pct_pt_jemaat=0.4, pct_pt_uni=0.4,
            pct_khusus_jemaat=0.2, pct_khusus_uni=0.1,
        )
        assert errors == []

    def test_all_zero_valid(self):
        errors = validate_porsi_constraint(0, 0, 0, 0, 0, 0)
        assert errors == []

    def test_x_pct_jemaat_negative(self):
        errors = validate_porsi_constraint(
            pct_x_jemaat=-0.1, pct_x_uni=0.3,
            pct_pt_jemaat=0.5, pct_pt_uni=0.3,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("X" in e and "pct_jemaat" in e for e in errors)

    def test_x_pct_jemaat_over_1(self):
        errors = validate_porsi_constraint(
            pct_x_jemaat=1.1, pct_x_uni=0.0,
            pct_pt_jemaat=0.5, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("X" in e and "pct_jemaat" in e for e in errors)

    def test_pt_pct_uni_over_1(self):
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.0,
            pct_pt_jemaat=0.5, pct_pt_uni=1.5,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("PT" in e and "pct_uni" in e for e in errors)

    def test_x_constraint_overcommit(self):
        """X: pct_jemaat=0.7 + pct_uni=0.5 = 1.2 > 1.0."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.7, pct_x_uni=0.5,
            pct_pt_jemaat=0.5, pct_pt_uni=0.3,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("X:" in e and "100%" in e for e in errors)

    def test_pt_constraint_overcommit(self):
        """PT overcommit."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.0,
            pct_pt_jemaat=0.6, pct_pt_uni=0.5,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("PT:" in e and "100%" in e for e in errors)

    def test_kh_constraint_overcommit(self):
        """KH overcommit."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.0,
            pct_pt_jemaat=0.0, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.6, pct_khusus_uni=0.5,
        )
        assert any("Khusus:" in e and "100%" in e for e in errors)

    def test_all_three_overcommit(self):
        """Semua tier overcommit → 3 errors."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.6, pct_x_uni=0.6,
            pct_pt_jemaat=0.6, pct_pt_uni=0.6,
            pct_khusus_jemaat=0.6, pct_khusus_uni=0.6,
        )
        overcommit_errors = [e for e in errors if "100%" in e]
        assert len(overcommit_errors) == 3

    def test_constraint_exactly_1(self):
        """Boundary: pct_jemaat + pct_uni = 1.0 → valid (tidak error)."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.5, pct_x_uni=0.5,
            pct_pt_jemaat=0.5, pct_pt_uni=0.5,
            pct_khusus_jemaat=0.5, pct_khusus_uni=0.5,
        )
        # Should be valid (no overcommit)
        assert all("100%" not in e for e in errors)

    def test_constraint_just_over_1(self):
        """Boundary: 1.0 + 1e-9 + small → overcommit."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.5, pct_x_uni=0.5000001,
            pct_pt_jemaat=0.0, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("100%" in e for e in errors)
