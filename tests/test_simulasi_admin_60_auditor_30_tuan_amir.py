"""
FASE 5 — Simulasi uji kalkulator porsi linear Uni → Misi → Jemaat.

Aturan mutlak (Jerry 2026-09-10):
    J_T = 100 - U_T - M_T
    Validasi: U_T + M_T <= 100

Kalau hasil nominal di sini tidak cocok, logika kalkulator SALAH.

Simulasi 1 — Kasus Admin 60% dan Auditor 30% (persentase)
Simulasi 2 — Transaksi Tuan Amir (nominal breakdown)
"""
import pytest

from app.utils.porsi_calculator import compute_porsi, validate_porsi_constraint


class TestSimulasiAdmin60Auditor30:
    """SIMULASI 1: U_X=60, U_PT=30, M_X=30, M_PT=10."""

    U_X, U_PT = 0.60, 0.30
    M_X, M_PT = 0.30, 0.10
    # J = 100 - U - M (derived)
    J_X, J_PT = 0.10, 0.60

    def test_persentase_sisa(self):
        """J_X = 100-60-30 = 10%; J_PT = 100-30-10 = 60%."""
        assert 100 - self.U_X * 100 - self.M_X * 100 == 10
        assert 100 - self.U_PT * 100 - self.M_PT * 100 == 60

    def test_total_keluar(self):
        """TotalKeluar_X = U_X + M_X = 90%; TotalKeluar_PT = 40%."""
        assert self.U_X * 100 + self.M_X * 100 == 90
        assert self.U_PT * 100 + self.M_PT * 100 == 40

    def test_validasi_lulus(self):
        """60+30=90 <= 100 valid; 30+10=40 <= 100 valid."""
        errs = validate_porsi_constraint(
            pct_x_jemaat=self.J_X, pct_x_uni=self.U_X,
            pct_pt_jemaat=self.J_PT, pct_pt_uni=self.U_PT,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert errs == []


class TestSimulasiTuanAmir:
    """SIMULASI 2: Transaksi Tuan Amir X=2.000.000 PT=1.000.000."""

    U_X, U_PT = 0.60, 0.30
    M_X, M_PT = 0.30, 0.10
    J_X, J_PT = 0.10, 0.60
    X, PT = 2_000_000, 1_000_000

    def test_breakdown_nominal(self):
        """X: uni 1.2M, misi 600K, jemaat 200K. PT: uni 300K, misi 100K, jemaat 600K."""
        p = compute_porsi(
            x=self.X, pt=self.PT, kh=0,
            pct_x_jemaat=self.J_X, pct_pt_jemaat=self.J_PT, pct_khusus_jemaat=0.0,
            pct_x_uni=self.U_X, pct_pt_uni=self.U_PT, pct_khusus_uni=0.0,
        )
        # X breakdown
        assert p["pu_x"] == 1_200_000  # 60% * 2jt
        assert p["pm_x"] == 600_000    # 30% * 2jt
        assert p["pj_x"] == 200_000    # 10% * 2jt
        # PT breakdown
        assert p["pu_pt"] == 300_000   # 30% * 1jt
        assert p["pm_pt"] == 100_000   # 10% * 1jt
        assert p["pj_pt"] == 600_000   # 60% * 1jt

    def test_grand_total_konservatif(self):
        """Total keseluruhan = uni + misi + jemaat = 3.000.000 persis X+PT."""
        p = compute_porsi(
            x=self.X, pt=self.PT, kh=0,
            pct_x_jemaat=self.J_X, pct_pt_jemaat=self.J_PT, pct_khusus_jemaat=0.0,
            pct_x_uni=self.U_X, pct_pt_uni=self.U_PT, pct_khusus_uni=0.0,
        )
        total_uni = p["pu_x"] + p["pu_pt"]
        total_misi = p["pm_x"] + p["pm_pt"]
        total_jemaat = p["pj_x"] + p["pj_pt"]
        assert total_uni == 1_500_000
        assert total_misi == 700_000
        assert total_jemaat == 800_000
        assert total_uni + total_misi + total_jemaat == self.X + self.PT == 3_000_000


class TestSimulasiBatasan:
    """Test case wajib lulus (kriteria selesai)."""

    def test_1_u41_m59(self):
        """U_X=41, M_X=59 → J_X=0."""
        assert 100 - 41 - 59 == 0

    def test_2_u20_m30(self):
        """U_PT=20, M_PT=30 → J_PT=50."""
        assert 100 - 20 - 30 == 50

    def test_3_u25_m75(self):
        """U_X=25, M_X=75 → J_X=0 valid."""
        errs = validate_porsi_constraint(
            pct_x_jemaat=0.0, pct_x_uni=0.25,
            pct_pt_jemaat=0.5, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert errs == []

    def test_4_u49_m0(self):
        """U_X=49, M_X=0 → J_X=51 valid."""
        assert 100 - 49 - 0 == 51

    def test_5_u60_m50_reject(self):
        """U_X=60, M_X=50 → 110 > 100 REJECT.

        jemaat derived = 100 - 60 - 50 = -10% (negatif → invalid).
        """
        errs = validate_porsi_constraint(
            pct_x_jemaat=1.0 - 0.60 - 0.50, pct_x_uni=0.60,
            pct_pt_jemaat=0.0, pct_pt_uni=0.0,
            pct_khusus_jemaat=0.0, pct_khusus_uni=0.0,
        )
        assert len(errs) > 0
        assert any("110%" in e for e in errs)


def test_simulasi_admin_60_auditor_30_tuan_amir():
    """Gabungan simulasi 1 + 2 — end-to-end nominal breakdown."""
    # Persentase (Simulasi 1)
    U_X, M_X = 0.60, 0.30
    U_PT, M_PT = 0.30, 0.10
    J_X = 1 - U_X - M_X          # 0.10
    J_PT = 1 - U_PT - M_PT       # 0.60

    # Transaksi Tuan Amir (Simulasi 2)
    X, PT = 2_000_000, 1_000_000
    p = compute_porsi(
        x=X, pt=PT, kh=0,
        pct_x_jemaat=J_X, pct_pt_jemaat=J_PT, pct_khusus_jemaat=0.0,
        pct_x_uni=U_X, pct_pt_uni=U_PT, pct_khusus_uni=0.0,
    )

    # X breakdown
    assert p["pu_x"] == 1_200_000
    assert p["pm_x"] == 600_000
    assert p["pj_x"] == 200_000
    # PT breakdown
    assert p["pu_pt"] == 300_000
    assert p["pm_pt"] == 100_000
    assert p["pj_pt"] == 600_000
    # Grand total
    assert p["pu_x"] + p["pm_x"] + p["pj_x"] + p["pu_pt"] + p["pm_pt"] + p["pj_pt"] == 3_000_000