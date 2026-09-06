"""
FASE 5 Sprint 5 — Integration tests for high-LOC endpoints in app/api/v1/kuitansi.py.

Targets endpoints with zero existing coverage:
- GET  /api/v1/kuitansi/{id}/pdf              (lines 502-777, 275 LOC)
- POST /api/v1/kuitansi/{id}/recompute-porsi (lines 1114-1262, 148 LOC)

Each test exercises:
- Happy path
- RBAC scope (cross-tenant denial)
- Not-found / purged
- Idempotency
"""



class TestKuitansiPdfEndpoint:
    """GET /api/v1/kuitansi/{id}/pdf — single-kuitansi PDF generation."""

    def test_pdf_happy_path_returns_pdf_binary(
        self, client, bendahara_token, jemaat_a, create_kuitansi
    ) -> None:
        """Bendahara can download PDF for their own kuitansi."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=200000, pt_angka=100000)
        resp = client.get(
            f"/api/v1/kuitansi/{k.id}/pdf",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        # PDF magic bytes
        assert resp.content[:4] == b"%PDF"

    def test_pdf_not_found(self, client, bendahara_token, jemaat_a) -> None:
        """Non-existent kuitansi ID → 404."""
        resp = client.get(
            "/api/v1/kuitansi/999999/pdf",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_pdf_cross_tenant_blocked(
        self, client, bendahara_token, jemaat_a, jemaat_b, create_kuitansi
    ) -> None:
        """Bendahara cannot download PDF for kuitansi from another tenant."""
        k_other = create_kuitansi(jemaat_b.id, perpuluhan_x_angka=50000)
        resp = client.get(
            f"/api/v1/kuitansi/{k_other.id}/pdf",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404
        assert "tidak ditemukan" in resp.json()["detail"].lower()

    def test_pdf_requires_auth(self, client, jemaat_a, create_kuitansi) -> None:
        """Unauthenticated request → 401."""
        k = create_kuitansi(jemaat_a.id)
        resp = client.get(f"/api/v1/kuitansi/{k.id}/pdf")
        assert resp.status_code == 401


class TestRecomputePorsiSingleEndpoint:
    """POST /api/v1/kuitansi/{id}/recompute-porsi — admin/auditor only."""

    def test_recompute_denied_for_bendahara(self, client, bendahara_token, jemaat_a, create_kuitansi) -> None:
        """BENDAHARA cannot recompute — endpoint is for ADMIN_UNI / AUDITOR_MISI only."""
        k = create_kuitansi(jemaat_a.id)
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403
        assert "ADMIN_UNI" in resp.json()["detail"]

    def test_recompute_happy_path_admin_uni(self, client, admin_token, jemaat_a, create_kuitansi) -> None:
        """ADMIN_UNI can recompute kuitansi in own uni."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000, pt_angka=50000)
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["nomor_kuitansi"].startswith("KPT-TEST-")
        # Response carries before/after snapshot
        assert "before" in data
        assert "after" in data
        assert "changed" in data

    def test_recompute_happy_path_auditor_misi(
        self, client, auditor_token, jemaat_a, create_kuitansi
    ) -> None:
        """AUDITOR_MISI can recompute kuitansi in own misi."""
        k = create_kuitansi(jemaat_a.id)
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 200

    def test_recompute_not_found(self, client, admin_token, jemaat_a) -> None:
        """Non-existent kuitansi → 404."""
        resp = client.post(
            "/api/v1/kuitansi/999999/recompute-porsi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_recompute_purged_rejected(self, client, admin_token, jemaat_a, create_kuitansi) -> None:
        """Purged kuitansi cannot be recomputed."""
        from app.core.database import get_db

        k = create_kuitansi(jemaat_a.id)
        # Mark as purged via direct DB on the SAME session that the app uses
        db = next(client.app.dependency_overrides[get_db]())
        db.query(type(k)).filter(type(k).id == k.id).update({"is_purged": True})
        db.commit()
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400
        assert "purge" in resp.json()["detail"].lower()

    def test_recompute_idempotent(self, client, admin_token, jemaat_a, create_kuitansi) -> None:
        """Calling recompute twice with same config should not change data."""
        k = create_kuitansi(jemaat_a.id, perpuluhan_x_angka=100000)
        # First call
        resp1 = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        # Second call should be no-op
        resp2 = client.post(
            f"/api/v1/kuitansi/{k.id}/recompute-porsi",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        # after snapshot should be identical
        assert data1["after"] == data2["after"]
        assert data2["changed"] is False

    def test_recompute_requires_auth(self, client, jemaat_a, create_kuitansi) -> None:
        """Unauthenticated → 401."""
        k = create_kuitansi(jemaat_a.id)
        resp = client.post(f"/api/v1/kuitansi/{k.id}/recompute-porsi")
        assert resp.status_code == 401
