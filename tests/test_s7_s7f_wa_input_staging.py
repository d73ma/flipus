"""
FASE 5 Sprint 7 — Integration tests untuk app/api/v1/wa_input.py staging endpoints.

Covers:
- GET  /api/v1/kuitansi/staging — list (RBAC + tenant-scope)
- DELETE /api/v1/kuitansi/staging/{id} — delete (RBAC + not-found + audit)
- POST /api/v1/kuitansi/finalize-staging — finalize batch
"""

from app.core.security import encrypt_pii


def _make_staging_kuitansi(jemaat, test_db, **overrides):
    """Helper: buat Kuitansi staging (is_finalized=False, created_via='wa')."""
    from app.models.transaction import Kuitansi

    db = test_db()
    defaults = {
        "tenant_id": jemaat.id,
        "id_rekap_mingguan": "STG-2026-09-05",
        "nomor_kuitansi": "PENDING-1-1",
        "tanggal_sabat": "2026-09-05",
        "nama_umat_encrypted": encrypt_pii("Budi WA"),
        "perpuluhan_x_angka": 100000,
        "pt_angka": 50000,
        "khusus_angka": 0,
        "total_pemberian_angka": 150000,
        "status": "draft",
        "is_purged": False,
        "is_finalized": False,
        "created_via": "wa",
        "wa_sender": "6281234567890",
        "temp_nomor": "STG-00001",
        "staging_id": 12345,
    }
    defaults.update(overrides)
    k = Kuitansi(**defaults)
    db.add(k)
    db.commit()
    db.refresh(k)
    db.close()
    return k


class TestListStaging:
    """GET /api/v1/kuitansi/staging — list staging items (BENDAHARA only)."""

    def test_empty(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.get(
            "/api/v1/kuitansi/staging",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["items"] == []
        assert data["last_web_upload_at"] is None

    def test_lists_staging_items(self, client, bendahara_token, jemaat_a, test_db) -> None:
        _make_staging_kuitansi(jemaat_a, test_db)
        _make_staging_kuitansi(
            jemaat_a,
            test_db,
            nomor_kuitansi="PENDING-1-2",
            perpuluhan_x_angka=200000,
            pt_angka=0,
            total_pemberian_angka=200000,
        )
        resp = client.get(
            "/api/v1/kuitansi/staging",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        # Each item has decrypt nama + totals
        assert data["items"][0]["nama_pemberi"] == "Budi WA"
        assert data["items"][0]["total"] == 150000

    def test_excludes_finalized(self, client, bendahara_token, jemaat_a, test_db) -> None:
        _make_staging_kuitansi(jemaat_a, test_db)
        _make_staging_kuitansi(
            jemaat_a,
            test_db,
            nomor_kuitansi="PENDING-1-2",
            is_finalized=True,
        )
        resp = client.get(
            "/api/v1/kuitansi/staging",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_requires_bendahara(self, client, ketua_token) -> None:
        """KETUA_KEUANGAN cannot list staging (BENDAHARA only)."""
        resp = client.get(
            "/api/v1/kuitansi/staging",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client) -> None:
        resp = client.get("/api/v1/kuitansi/staging")
        assert resp.status_code == 401

    def test_tenant_scoped(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        _make_staging_kuitansi(jemaat_b, test_db)
        resp = client.get(
            "/api/v1/kuitansi/staging",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        # Bendahara A should not see tenant B's staging
        assert resp.json()["count"] == 0


class TestDeleteStaging:
    """DELETE /api/v1/kuitansi/staging/{id} — delete staging item."""

    def test_delete_happy_path(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.delete(
            f"/api/v1/kuitansi/staging/{k.id}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == k.id
        assert resp.json()["status"] == "ok"

    def test_delete_not_found(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.delete(
            "/api/v1/kuitansi/staging/999999",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_delete_cross_tenant_blocked(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_b, test_db)
        resp = client.delete(
            f"/api/v1/kuitansi/staging/{k.id}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_delete_finalized_rejected(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db, is_finalized=True)
        resp = client.delete(
            f"/api/v1/kuitansi/staging/{k.id}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_delete_requires_bendahara(self, client, ketua_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.delete(
            f"/api/v1/kuitansi/staging/{k.id}",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403

    def test_delete_audit_logged(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        client.delete(
            f"/api/v1/kuitansi/staging/{k.id}",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        # Audit log row should exist
        from app.models.audit import AuditLog

        db = test_db()
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "WA_STAGING_DELETE")
            .filter(AuditLog.id_rekap_mingguan == f"WA-STG-{k.id}")
            .first()
        )
        assert audit is not None
        db.close()


class TestFinalizeStaging:
    """POST /api/v1/kuitansi/finalize-staging — finalize batch."""

    def test_finalize_happy_path(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id]},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["finalized_count"] == 1
        assert data["items"][0]["id"] == k.id
        # nomor_kuitansi should be YYYYMMDD-{tenant:03d}-{counter:03d}
        assert data["items"][0]["nomor_kuitansi"].startswith("20260905")

    def test_finalize_empty_ids(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": []},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_finalize_not_found(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [999999]},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_finalize_sets_is_finalized(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id]},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        from app.models.transaction import Kuitansi

        db = test_db()
        refreshed = db.query(Kuitansi).get(k.id)
        assert refreshed.is_finalized is True
        assert refreshed.status == "finalized"
        assert refreshed.staging_id is None
        assert refreshed.temp_nomor is None
        db.close()

    def test_finalize_override_tanggal_sabat(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id], "tanggal_sabat": "2026-09-12"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"][0]["tanggal_sabat"] == "2026-09-12"

    def test_finalize_invalid_tanggal_format(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id], "tanggal_sabat": "invalid-date"},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_finalize_requires_bendahara(self, client, ketua_token, jemaat_a, test_db) -> None:
        k = _make_staging_kuitansi(jemaat_a, test_db)
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id]},
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403

    def test_finalize_cross_tenant_blocked(
        self, client, bendahara_token, jemaat_a, jemaat_b, test_db
    ) -> None:
        k = _make_staging_kuitansi(jemaat_b, test_db)
        resp = client.post(
            "/api/v1/kuitansi/finalize-staging",
            json={"staging_ids": [k.id]},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404
