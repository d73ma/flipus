"""
FASE 5 Sprint 5 — Additional integration tests for app/api/v1/master.py.

Targets:
- GET  /api/v1/master/persentase  (line 219) — get config
- POST /api/v1/master/persentase  (line 298) — set config
"""


class TestPersentaseConfig:
    """GET + POST /api/v1/master/persentase — read/write config."""

    def test_get_misi_config_auditor(self, client, auditor_token, misi_minahasa) -> None:
        """AUDITOR_MISI can read MISI scope config for own misi."""
        resp = client.get(
            "/api/v1/master/persentase",
            params={"scope": "MISI", "ref_id": misi_minahasa.id},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "MISI"
        assert data["ref_id"] == misi_minahasa.id

    def test_get_creates_default_if_missing(self, client, auditor_token, misi_minahasa) -> None:
        """If config doesn't exist, returns default values."""
        resp = client.get(
            "/api/v1/master/persentase",
            params={"scope": "MISI", "ref_id": misi_minahasa.id},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Default values: X=100% to Misi, PT=50%, Khusus=50%
        assert data["pct_x_jemaat"] == 1.0
        assert data["pct_pt_jemaat"] == 0.5

    def test_get_invalid_scope_400(self, client, auditor_token, misi_minahasa) -> None:
        """Invalid scope value → 400."""
        resp = client.get(
            "/api/v1/master/persentase",
            params={"scope": "INVALID", "ref_id": misi_minahasa.id},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 400

    def test_get_auditor_other_misi_via_db(self, client, auditor_token) -> None:
        """Auditor cannot view config for a misi they don't belong to.

        Create another misi in a DIFFERENT uni to ensure RBAC separation.
        """
        import uuid

        from app.core.database import get_db
        from app.models.master import MisiKonferens, Uni

        db = next(get_db())
        # Use unique kode to avoid collision
        suffix = uuid.uuid4().hex[:6]
        other_uni = Uni(kode=f"U{suffix}", nama_resmi=f"Other Uni {suffix}")
        db.add(other_uni)
        db.commit()
        db.refresh(other_uni)
        other_misi = MisiKonferens(
            uni_id=other_uni.id, kode=f"M{suffix}", nama_resmi=f"Other Misi {suffix}", jenis="MISI"
        )
        db.add(other_misi)
        db.commit()
        db.refresh(other_misi)
        other_id = other_misi.id
        db.close()
        resp = client.get(
            "/api/v1/master/persentase",
            params={"scope": "MISI", "ref_id": other_id},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 403

    def test_get_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get(
            "/api/v1/master/persentase",
            params={"scope": "MISI", "ref_id": 1},
        )
        assert resp.status_code == 401
