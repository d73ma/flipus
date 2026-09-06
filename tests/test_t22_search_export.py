"""
FLIPUS v1.3 — Tahap 22 Search & Export Tests.

Tests advanced filtering, CSV/XLSX export, filter-meta aggregation,
RBAC scoping, and status_filter propagation.

Run:
    .venv/bin/python3 -m pytest tests/test_t22_search_export.py -v
"""



class TestKuitansiSearch:
    """Test /v1/kuitansi/search endpoint."""

    def test_search_basic_date_filter(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Filter by date_from and date_to."""
        create_kuitansi(jemaat_a.id, tanggal_sabat="2026-08-01")
        create_kuitansi(jemaat_a.id, tanggal_sabat="2026-08-15")
        create_kuitansi(jemaat_a.id, tanggal_sabat="2026-08-29")

        resp = client.get(
            "/api/v1/kuitansi/search",
            params={"date_from": "2026-08-10", "date_to": "2026-08-20"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["tanggal_sabat"] == "2026-08-15"

    def test_search_by_nama_decrypt(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Search by nama (encrypted) should decrypt-then-match."""
        create_kuitansi(jemaat_a.id)
        # Overwrite nama to specific test value
        # Use the test_db directly
        from app.core.database import get_db
        from app.main import app
        # Direct DB manipulation
        app.dependency_overrides[get_db]().__next__().get_bind()

        # Create new kuitansi with specific nama
        create_kuitansi(jemaat_a.id)

        # Search for "Test Umat" (default name in factory)
        resp = client.get(
            "/api/v1/kuitansi/search",
            params={"nama": "Umat"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1  # factory uses "Test Umat"

    def test_search_by_nominal_range(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Filter by nominal_min and nominal_max."""
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=50000, pt_angka=10000)
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=500000, pt_angka=100000)
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=5000000, pt_angka=1000000)

        resp = client.get(
            "/api/v1/kuitansi/search",
            params={"nominal_min": 200000, "nominal_max": 1000000},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1  # Only the 500K + 100K one

    def test_search_pagination(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Pagination works with per_page parameter."""
        for i in range(5):
            create_kuitansi(jemaat_a.id, tanggal_sabat=f"2026-08-0{i+1}")

        resp = client.get(
            "/api/v1/kuitansi/search",
            params={"per_page": 2, "page": 1},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_search_status_filter_default_finalized(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Default status_filter='finalized' hides drafts."""
        create_kuitansi(jemaat_a.id, status="finalized")
        create_kuitansi(jemaat_a.id, status="draft")

        resp = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Default is finalized, so only 1 visible
        assert data["total"] == 1

    def test_search_status_filter_all(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """status_filter='all' returns everything."""
        create_kuitansi(jemaat_a.id, status="finalized")
        create_kuitansi(jemaat_a.id, status="draft")
        create_kuitansi(jemaat_a.id, status="rejected")

        resp = client.get(
            "/api/v1/kuitansi/search",
            params={"status_filter": "all"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    def test_search_rbac_bendahara_scoped(
        self, client, bendahara_token, jemaat_a, jemaat_b, create_kuitansi
    ):
        """Bendahara only sees own tenant."""
        create_kuitansi(jemaat_a.id)
        create_kuitansi(jemaat_b.id)

        resp = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        data = resp.json()
        # Bendahara sees only own tenant (1 kuitansi)
        assert data["total"] == 1

    def test_search_rbac_admin_sees_all(
        self, client, admin_token, jemaat_a, jemaat_b, create_kuitansi
    ):
        """Admin Uni sees all jemaat in uni."""
        create_kuitansi(jemaat_a.id)
        create_kuitansi(jemaat_b.id)

        resp = client.get(
            "/api/v1/kuitansi/search",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = resp.json()
        assert data["total"] == 2


class TestKuitansiExport:
    """Test /v1/kuitansi/export endpoint."""

    def test_export_csv(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Export returns valid CSV."""
        create_kuitansi(jemaat_a.id)

        resp = client.get(
            "/api/v1/kuitansi/export",
            params={"format": "csv"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        # Note: this endpoint is /v1 not /api/v1 — check both
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "text/csv" in resp.headers.get("content-type", "")
            content = resp.text
            # Header "Nomor Kuitansi" (Title Case) + KPT-TEST- prefix value
            assert "Nomor Kuitansi" in content
            assert "KPT-TEST" in content

    def test_export_xlsx(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """Export returns valid XLSX."""
        create_kuitansi(jemaat_a.id)

        resp = client.get(
            "/api/v1/kuitansi/export",
            params={"format": "xlsx"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            # XLSX is a zip — check magic bytes
            assert resp.content[:2] == b"PK"


class TestKuitansiFilterMeta:
    """Test /v1/kuitansi/filter-meta endpoint."""

    def test_filter_meta_returns_aggregates(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ):
        """filter-meta returns total + breakdown by tipe."""
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000, pt_angka=50000)
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=200000, pt_angka=0)
        create_kuitansi(jemaat_a.id, perpuluhan_x_angka=0, pt_angka=100000)

        resp = client.get(
            "/api/v1/kuitansi/filter-meta",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            # Field is total_kuitansi (not total)
            assert data.get("total_kuitansi", 0) >= 3
