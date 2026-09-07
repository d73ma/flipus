"""
FASE 5 Sprint 8 — Integration tests untuk POST /api/v1/kuitansi/quick-input.

Covers the v2.0 M1 PWA Quick Input endpoint (BENDAHARA only).
"""



class TestQuickInputCreate:
    """POST /api/v1/kuitansi/quick-input — single-step PWA kuitansi input."""

    def test_happy_path_auto_create_kategori(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi Santoso",
                "items": [
                    {"kategori_nama": "Persepuluhan", "nominal": 100000},
                    {"kategori_nama": "Bantuan Pendidikan", "nominal": 50000},
                ],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["total_pemberian"] == 150000
        assert data["nomor_kuitansi"]  # non-empty
        # New kategori auto-created
        assert len(data["kategori_baru"]) == 2
        assert len(data["kategori_existing"]) == 0

    def test_reuse_existing_kategori(self, client, bendahara_token, jemaat_a) -> None:
        # First call creates kategori
        client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 100000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        # Second call with same kategori → existing
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Andi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 200000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["kategori_baru"]) == 0
        assert len(data["kategori_existing"]) == 1

    def test_empty_items(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={"nama_pemberi": "Budi", "items": []},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_all_zero_nominal(self, client, bendahara_token, jemaat_a) -> None:
        """Items with nominal=0 filtered → no valid items → 400."""
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 0}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_empty_nama(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_nama_too_long(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "x" * 101,
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_non_bendahara_forbidden(self, client, ketua_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
            },
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
            },
        )
        assert resp.status_code == 401

    def test_invalid_tanggal_sabat(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
                "tanggal_sabat": "invalid-date",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_override_tanggal_sabat(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1000}],
                "tanggal_sabat": "2026-09-12",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["tanggal_sabat"] == "2026-09-12"

    def test_created_kuitansi_in_db(self, client, bendahara_token, jemaat_a, test_db) -> None:
        client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 100000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        from app.models.transaction import Kuitansi

        db = test_db()
        k = db.query(Kuitansi).filter(Kuitansi.created_via == "pwa").first()
        assert k is not None
        assert k.tenant_id == jemaat_a.id
        assert k.total_pemberian_angka == 100000
        assert k.status == "finalized"
        db.close()


class TestQuickInputItemValidation:
    """Pydantic schema validation on QuickInputItem."""

    def test_negative_nominal(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": -100}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 422

    def test_nominal_too_large(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "Persepuluhan", "nominal": 1_000_000_000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 422

    def test_empty_kategori_nama(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/quick-input",
            json={
                "nama_pemberi": "Budi",
                "items": [{"kategori_nama": "   ", "nominal": 1000}],
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 422
