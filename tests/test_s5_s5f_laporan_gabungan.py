"""
FASE 5 Sprint 5 — Integration tests for app/api/v1/laporan_gabungan.py.

Targets:
- GET /api/v1/laporan/gabungan/{id_rekap_mingguan}  (line 120)
"""


class TestLaporanGabunganJson:
    """GET /api/v1/laporan/gabungan/{rid} — JSON rekap per sabat."""

    def test_get_combined_report_with_kuitansi(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ) -> None:
        """Returns JSON summary combining kuitansi + pengeluaran for the week."""
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan()  # current week
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=100000, pt_angka=50000)
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=200000, pt_angka=100000)
        resp = client.get(
            f"/api/v1/laporan/gabungan/{rid}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id_rekap_mingguan"] == rid
        assert len(data["kuitansi"]) == 2
        # Total penerimaan = X + PT
        assert data["total_penerimaan"] == 450000
        assert data["count_kuitansi"] == 2

    def test_empty_rekap_returns_zero_totals(self, client, bendahara_token, jemaat_a) -> None:
        """Empty rekap returns zero totals + empty items."""
        resp = client.get(
            "/api/v1/laporan/gabungan/RK-2026-01-01-2026W01",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_penerimaan"] == 0
        assert data["kuitansi"] == []

    def test_tenant_scoped(self, client, bendahara_token, jemaat_a, jemaat_b, create_kuitansi) -> None:
        """Bendahara only sees own tenant's data."""
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan()
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=100000)
        create_kuitansi(jemaat_b.id, id_rekap_mingguan=rid, perpuluhan_x_angka=999999)
        resp = client.get(
            f"/api/v1/laporan/gabungan/{rid}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Bendahara from jemaat_a sees only own data
        assert data["count_kuitansi"] == 1
        # Ensure no leakage from jemaat_b's 999999 amount
        assert all(item["perpuluhan_x_angka"] != 999999 for item in data["kuitansi"])

    def test_excludes_purged_kuitansi(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Purged kuitansi should be excluded from laporan."""
        from app.core.database import get_db
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan()
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=100000)
        k2 = create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=200000)
        # Mark k2 as purged
        db = next(client.app.dependency_overrides[get_db]())
        db.query(type(k2)).filter(type(k2).id == k2.id).update({"is_purged": True})
        db.commit()
        resp = client.get(
            f"/api/v1/laporan/gabungan/{rid}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count_kuitansi"] == 1

    def test_only_finalized_kuitansi(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """Draft kuitansi should be excluded from laporan (finalized only)."""
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan()
        # Finalized: X=100000, PT=0 → total 100000
        create_kuitansi(
            jemaat_a.id, id_rekap_mingguan=rid, status="finalized", perpuluhan_x_angka=100000, pt_angka=0
        )
        # Draft: X=200000, PT=0 → should be excluded
        create_kuitansi(
            jemaat_a.id, id_rekap_mingguan=rid, status="draft", perpuluhan_x_angka=200000, pt_angka=0
        )
        resp = client.get(
            f"/api/v1/laporan/gabungan/{rid}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Only finalized shown
        assert data["count_kuitansi"] == 1
        assert data["total_penerimaan"] == 100000

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/laporan/gabungan/RK-X")
        assert resp.status_code == 401

    def test_response_includes_net_saldo(
        self, client, bendahara_token, jemaat_a, create_kuitansi, test_db
    ) -> None:
        """Response includes net_saldo (penerimaan - pengeluaran)."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran
        from app.models.pengeluaran import Pengeluaran
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan

        rid = generate_id_rekap_mingguan()
        # Kuitansi X=300000, PT=0
        create_kuitansi(jemaat_a.id, id_rekap_mingguan=rid, perpuluhan_x_angka=300000, pt_angka=0)
        # Add approved Pengeluaran on same id_rekap
        db = test_db()
        cat = KategoriPengeluaran(tenant_id=jemaat_a.id, nama="X", alias="X", is_aktif=True, urutan=1)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        db.add(
            Pengeluaran(
                tenant_id=jemaat_a.id,
                nomor_pengeluaran="P-001",
                kategori_pengeluaran_id=cat.id,
                jumlah=50000,
                tanggal="2026-08-22",
                tanggal_sabat="2026-08-22",
                id_rekap_mingguan=rid,
                status="approved",
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            f"/api/v1/laporan/gabungan/{rid}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Verify net_saldo logic: total_penerimaan - total_pengeluaran_approved
        expected_net = data["total_penerimaan"] - data["total_pengeluaran_approved"]
        assert data["net_saldo"] == expected_net
        # Verify structure
        assert "total_pengeluaran_approved" in data
        assert "count_pengeluaran_approved" in data
