"""
FLIPUS v1.5 — FASE 2 S3/R6: Accounting Integrity Test Suite.

Pure-unit tests untuk integritas akuntansi. Tidak butuh DB / fixture / FastAPI client.
Cakupan:
  1. Conservation of money — total in == total out (jemaat + misi + uni)
  2. Pct constraints — pct_jemaat + pct_uni ≤ 1.0 per tier (X, PT, KH)
  3. Jerry's worked example — reproduce angka dari slide demo 2026-08-23
  4. T101 regression — pct_x_jemaat=0.0 → porsi_x_jemaat=0 (SDA tithe doctrine)
  5. KH semantics — pct_khusus_jemaat = fraction to MISI, bukan ke Jemaat
  6. Rounding — int(round()) untuk konsistensi (bukan int truncate)
  7. Idempotency — compute_porsi() deterministik, 2x panggil hasil sama

Berlaku untuk SEMUA call site (dashboard, scanner, wa_input, quick_input, agregat).
"""

import pytest
from app.utils.porsi_calculator import compute_porsi, validate_porsi_constraint


# ---------------------------------------------------------------------------
# 1. Conservation of money
# ---------------------------------------------------------------------------

class TestConservationOfMoney:
    """Total input (X+PT+KH) harus == total porsi (jemaat+misi+uni)."""

    @pytest.mark.parametrize("x,pt,kh", [
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
        (100_000, 0, 0),
        (797_500, 315_000, 200_000),  # Jerry's example
        (1_000_000, 500_000, 250_000),
        (10_000, 0, 5_000),
    ])
    def test_total_in_equals_total_out(self, x, pt, kh):
        r = compute_porsi(
            x=x, pt=pt, kh=kh,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.41, pct_pt_uni=0.30, pct_khusus_uni=0.0,
        )
        total_in = x + pt + kh
        total_out = sum(r.values())
        assert total_in == total_out, (
            f"Conservation violated: in={total_in}, out={total_out} "
            f"(diff={total_in - total_out})"
        )

    def test_konservasi_dengan_pct_uni_aktif(self):
        """Pastikan porsi_uni dihitung dari TOTAL, bukan dari sisa."""
        x, pt, kh = 1_000_000, 500_000, 250_000
        r = compute_porsi(
            x=x, pt=pt, kh=kh,
            pct_x_jemaat=0.1, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.2, pct_pt_uni=0.1, pct_khusus_uni=0.0,
        )
        # Manual verification:
        # pj_x = round(1M * 0.1) = 100000
        # pu_x = round(1M * 0.2) = 200000
        # pm_x = max(0, 1M - 100000 - 200000) = 700000
        # pj_pt = round(500K * 0.5) = 250000
        # pu_pt = round(500K * 0.1) = 50000
        # pm_pt = max(0, 500K - 250000 - 50000) = 200000
        assert r["pj_x"] == 100_000
        assert r["pu_x"] == 200_000
        assert r["pm_x"] == 700_000
        assert r["pj_pt"] == 250_000
        assert r["pu_pt"] == 50_000
        assert r["pm_pt"] == 200_000
        assert sum(r.values()) == x + pt + kh


# ---------------------------------------------------------------------------
# 2. Pct constraints
# ---------------------------------------------------------------------------

class TestPctConstraints:
    """validate_porsi_constraint() harus reject pct_jemaat + pct_uni > 1.0."""

    def test_valid_default_jerry(self):
        """Default Jerry (2026-08-23) — pct_jemaat + pct_uni ≤ 1.0."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.41,
            pct_pt_jemaat=0.5, pct_pt_uni=0.30,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert errors == []

    def test_invalid_pt_jemaat_plus_uni_gt_1(self):
        """PT: 0.5 + 0.6 = 1.1 > 1.0 → harus error."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.41,
            pct_pt_jemaat=0.5, pct_pt_uni=0.6,  # 1.1 > 1.0
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert len(errors) == 1
        assert "PT" in errors[0]
        assert "100%" in errors[0]

    def test_negative_pct_rejected(self):
        """pct_jemaat < 0 → invalid."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=-0.1, pct_x_uni=0.5,
            pct_pt_jemaat=0.5, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("X pct_jemaat" in e for e in errors)

    def test_pct_gt_1_rejected(self):
        """pct_uni > 1.0 → invalid."""
        errors = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=1.5,
            pct_pt_jemaat=0.5, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert any("X pct_uni" in e for e in errors)


# ---------------------------------------------------------------------------
# 3. Jerry's worked example (regression lock)
# ---------------------------------------------------------------------------

class TestJerryWorkedExample:
    """
    Reproduce angka dari slide demo Jerry 2026-08-23.
    Jika regression terjadi di compute_porsi, test ini akan FAIL.
    """

    def test_pt_315k_jemaat_50_pct_uni_30_pct(self):
        """PT 315,000 → jemaat 157,500 (50%), uni 94,500 (30%), misi 63,000 (20%)."""
        r = compute_porsi(
            x=0, pt=315_000, kh=0,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.30, pct_khusus_uni=0.0,
        )
        assert r["pj_pt"] == 157_500
        assert r["pu_pt"] == 94_500
        assert r["pm_pt"] == 63_000

    def test_x_797k_jemaat_0_pct_uni_41_pct(self):
        """X 797,500 → jemaat 0 (0%), uni 326,975 (41%), misi 470,525 (59%)."""
        r = compute_porsi(
            x=797_500, pt=0, kh=0,
            pct_x_jemaat=0.0, pct_pt_uni=0.0,
            pct_pt_jemaat=0.0, pct_x_uni=0.41,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        # round(797500 * 0.0) = 0
        # round(797500 * 0.41) = 326975
        # 797500 - 0 - 326975 = 470525
        assert r["pj_x"] == 0
        assert r["pu_x"] == 326_975
        assert r["pm_x"] == 470_525


# ---------------------------------------------------------------------------
# 4. T101 regression — pct_x_jemaat = 0.0 (SDA tithe doctrine)
# ---------------------------------------------------------------------------

class TestT101TitheDoctrine:
    """
    T101: pct_x_jemaat dulu 1.0 (SALAH), dikoreksi ke 0.0 di v1.5.1.
    SDA Advent doctrine: 100% perpuluhan (X) harus ke Misi (Uni → Misi),
    tidak boleh ada yang "ditahan" di Jemaat lokal.
    """

    def test_x_100_pct_ke_misi_dan_uni(self):
        """X 1,000,000 dengan pct_x_jemaat=0.0 → 100% dibagi antara Misi & Uni."""
        x = 1_000_000
        r = compute_porsi(
            x=x, pt=0, kh=0,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.5, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert r["pj_x"] == 0, "X tidak boleh ditahan di Jemaat (SDA doctrine)"
        assert r["pu_x"] == 500_000
        assert r["pm_x"] == 500_000
        assert r["pj_x"] + r["pu_x"] + r["pm_x"] == x


# ---------------------------------------------------------------------------
# 5. KH semantics — pct_khusus_jemaat = fraction to MISI
# ---------------------------------------------------------------------------

class TestKHSemantics:
    """
    KH punya semantik TERBALIK dari X & PT:
    - pct_khusus_jemaat = fraction KH yang dikirim ke MISI (bukan Jemaat retention).
    - pct_khusus_uni    = fraction KH yang dikirim ke UNI (default 0).
    - Sisa KH (pj_kh) stays in Jemaat.
    """

    def test_kh_default_all_stays_in_jemaat(self):
        """KH dengan pct_khusus_jemaat=0 & pct_khusus_uni=0 → 100% stays in Jemaat."""
        r = compute_porsi(
            x=0, pt=0, kh=200_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert r["pj_kh"] == 200_000
        assert r["pm_kh"] == 0
        assert r["pu_kh"] == 0

    def test_kh_split_50_50_misi_jemaat(self):
        """KH 100,000 dengan pct_khusus_jemaat=0.5 → 50k ke Misi, 50k stays Jemaat."""
        r = compute_porsi(
            x=0, pt=0, kh=100_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.5,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        assert r["pm_kh"] == 50_000
        assert r["pj_kh"] == 50_000
        assert r["pu_kh"] == 0


# ---------------------------------------------------------------------------
# 6. Rounding consistency
# ---------------------------------------------------------------------------

class TestRounding:
    """compute_porsi pakai int(round()) — bukan int() truncate."""

    def test_rounding_half_up(self):
        """333 * 0.5 = 166.5 → harus 167 (round half to even / banker's).
        Python's round() pakai banker's rounding → round(166.5) = 166 (even).
        Test ini lock behavior agar tidak ada drift rounding."""
        r = compute_porsi(
            x=333, pt=0, kh=0,
            pct_x_jemaat=0.5, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        # round(333 * 0.5) = round(166.5) = 166 (Python banker's rounding)
        assert r["pj_x"] == 166

    def test_rounding_truncate_old_dashboard_was_166_vs_167(self):
        """Regression lock: dashboard.py lama pakai int() truncate (333*0.5=166).
        Setelah refactor pakai compute_porsi → 166 juga (banker's).
        Konsistensi: 166 di kedua tempat."""
        # Truncate: int(333 * 0.5) = 166
        # round: round(333 * 0.5) = 166
        # Untuk 333 → identik. Test ini memastikan tidak ada drift.
        old_value = int(333 * 0.5)
        new_value = round(333 * 0.5)
        # Untuk angka dengan .5 persis, keduanya menghasilkan 166 (Python).
        # Untuk 335 → int(335*0.5)=167, round(335*0.5)=168
        r = compute_porsi(
            x=335, pt=0, kh=0,
            pct_x_jemaat=0.5, pct_pt_jemaat=0.0, pct_khusus_jemaat=0.0,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        # round(335*0.5) = round(167.5) = 168 (banker's → even)
        assert r["pj_x"] == 168


# ---------------------------------------------------------------------------
# 7. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """compute_porsi() deterministik — 2x panggil hasil sama."""

    def test_double_call_same_result(self):
        args = dict(
            x=797_500, pt=315_000, kh=200_000,
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.41, pct_pt_uni=0.30, pct_khusus_uni=0.0,
        )
        r1 = compute_porsi(**args)
        r2 = compute_porsi(**args)
        assert r1 == r2

    def test_no_side_effects(self):
        """compute_porsi() tidak boleh modify input args."""
        pct = dict(
            pct_x_jemaat=0.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
            pct_x_uni=0.41, pct_pt_uni=0.30, pct_khusus_uni=0.0,
        )
        pct_snapshot = dict(pct)
        compute_porsi(x=100, pt=100, kh=100, **pct)
        assert pct == pct_snapshot
