"""
FASE 5 Sprint 5 — Integration tests for high-LOC endpoints in app/api/v1/reports.py.

Targets:
- GET  /api/v1/reports/sabat-info          (line 88)
- GET  /api/v1/reports/mingguan            (line 140)
- GET  /api/v1/reports/summary             (line 201)

Endpoint POST /api/v1/reports/blast-weekly diluar scope (butuh Fonnte mocking
kompleks + idempotency state — bisa Sprint 6).
"""

from datetime import datetime


class TestSabatInfoEndpoint:
    """GET /api/v1/reports/sabat-info — info sabat + next_urutan_hint."""

    def test_returns_sabat_info_with_hint(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Sabat info should return sabat_ke, tanggal_sabat, next_urutan_hint."""
        resp = client.get(
            "/api/v1/reports/sabat-info",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["hari"] == "Sabtu"
        assert "sabat_ke" in data
        assert "tanggal_sabat" in data
        assert "bulan_romawi" in data
        assert "bulan_nama" in data
        assert "next_urutan_hint" in data

    def test_next_urutan_hint_increments_with_existing_kuitansi(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ) -> None:
        """When kuitansi exist for current sabat, hint should be count+1."""
        from app.utils.sabat_counter import get_current_sabat

        sabat_tgl = get_current_sabat()["tanggal_sabat"]
        create_kuitansi(jemaat_a.id, tanggal_sabat=sabat_tgl)
        create_kuitansi(jemaat_a.id, tanggal_sabat=sabat_tgl)
        resp = client.get(
            "/api/v1/reports/sabat-info",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # At least 3 (2 created + 1 base)
        assert data["next_urutan_hint"] >= 3

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/reports/sabat-info")
        assert resp.status_code == 401


class TestLaporanMingguanEndpoint:
    """GET /api/v1/reports/mingguan?id_rekap_mingguan=X — rekap per Sabat."""

    def test_mingguan_default_finalized(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Default status_filter='finalized' returns only finalized kuitansi."""
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan(datetime(2026, 8, 22))
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, tanggal_sabat="2026-08-22", status="finalized")
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, tanggal_sabat="2026-08-22", status="draft")
        resp = client.get(
            "/api/v1/reports/mingguan",
            params={"id_rekap_mingguan": rid},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Default finalized only — items list should have only 1
        assert len(data["items"]) == 1

    def test_mingguan_status_all(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """status_filter='all' returns both draft and finalized."""
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan(datetime(2026, 8, 22))
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, tanggal_sabat="2026-08-22", status="finalized")
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, tanggal_sabat="2026-08-22", status="draft")
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, tanggal_sabat="2026-08-22", status="draft")
        resp = client.get(
            "/api/v1/reports/mingguan",
            params={"id_rekap_mingguan": rid, "status_filter": "all"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3

    def test_mingguan_not_found(self, client, bendahara_token, jemaat_a) -> None:
        """Non-existent id_rekap_mingguan → 404."""
        resp = client.get(
            "/api/v1/reports/mingguan",
            params={"id_rekap_mingguan": "RK-99999999-9999W99"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_mingguan_invalid_status_filter(self, client, bendahara_token, jemaat_a) -> None:
        """Invalid status_filter → 400."""
        resp = client.get(
            "/api/v1/reports/mingguan",
            params={"id_rekap_mingguan": "RK-X", "status_filter": "garbage"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_mingguan_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get(
            "/api/v1/reports/mingguan",
            params={"id_rekap_mingguan": "RK-X"},
        )
        assert resp.status_code == 401


class TestSummaryEndpoint:
    """GET /api/v1/reports/summary?bulan=YYYY-MM — dashboard ringkasan per bulan."""

    def test_summary_default_current_month(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Default bulan=current YYYY-MM returns aggregated kuitansi."""
        current_month = datetime.now().strftime("%Y-%m")
        create_kuitansi(
            jemaat_a.id, tanggal_sabat=f"{current_month}-15", perpuluhan_x_angka=100000, pt_angka=50000
        )
        create_kuitansi(
            jemaat_a.id, tanggal_sabat=f"{current_month}-22", perpuluhan_x_angka=200000, pt_angka=75000
        )
        resp = client.get(
            "/api/v1/reports/summary",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bulan"] == current_month
        assert data["nama_jemaat"] == jemaat_a.nama_jemaat_lokal
        assert data["jumlah_kuitansi"] == 2
        assert data["grand_total_x"] == 300000
        assert data["grand_total_pt"] == 125000

    def test_summary_filter_by_month(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Bulan filter should exclude kuitansi outside that month."""
        create_kuitansi(jemaat_a.id, tanggal_sabat="2026-08-15")
        create_kuitansi(jemaat_a.id, tanggal_sabat="2026-09-05")
        resp = client.get(
            "/api/v1/reports/summary",
            params={"bulan": "2026-08"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jumlah_kuitansi"] == 1

    def test_summary_empty_month(self, client, bendahara_token, jemaat_a) -> None:
        """Month with no kuitansi should return zero aggregates."""
        resp = client.get(
            "/api/v1/reports/summary",
            params={"bulan": "2020-01"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["jumlah_kuitansi"] == 0
        assert data["grand_total_x"] == 0
        assert data["grand_total_pt"] == 0

    def test_summary_excludes_purged(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Purged kuitansi should not count in summary."""
        from app.core.database import get_db

        current_month = datetime.now().strftime("%Y-%m")
        create_kuitansi(jemaat_a.id, tanggal_sabat=f"{current_month}-10")
        k2 = create_kuitansi(jemaat_a.id, tanggal_sabat=f"{current_month}-17")
        # Purge k2
        db = next(client.app.dependency_overrides[get_db]())
        db.query(type(k2)).filter(type(k2).id == k2.id).update({"is_purged": True})
        db.commit()
        resp = client.get(
            "/api/v1/reports/summary",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["jumlah_kuitansi"] == 1

    def test_summary_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/reports/summary")
        assert resp.status_code == 401
