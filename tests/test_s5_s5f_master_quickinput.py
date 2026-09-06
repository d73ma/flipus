"""
FASE 5 Sprint 5 — Integration tests for app/api/v1/master.py and quick_input.py.

Targets simple list endpoints with zero existing coverage:
- GET /api/v1/master/uni                     (line 50)
- GET /api/v1/master/misi                    (line 62)
- GET /api/v1/kategori/list                  (quick_input.py line 369)
"""



class TestMasterUniEndpoint:
    """GET /api/v1/master/uni — list 3 Uni untuk dropdown."""

    def test_list_uni_returns_seeded(self, client, uni_dk) -> None:
        """Public endpoint returns Uni list (no auth required)."""
        resp = client.get("/api/v1/master/uni")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # uni_dk fixture seeded "UKIKT"
        assert any(u["kode"] == "UKIKT" for u in data)

    def test_uni_no_auth_required(self, client) -> None:
        """Public endpoint — no JWT needed."""
        resp = client.get("/api/v1/master/uni")
        # Should not be 401
        assert resp.status_code != 401


class TestMasterMisiEndpoint:
    """GET /api/v1/master/misi — list Misi Konferens."""

    def test_list_misi_all(self, client, uni_dk, misi_minahasa) -> None:
        """List all Misi without filter."""
        resp = client.get("/api/v1/master/misi")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(m["kode"] == "DK.MIN" for m in data)

    def test_list_misi_filter_by_uni(self, client, uni_dk, misi_minahasa) -> None:
        """Filter by uni_id returns only Misi for that Uni."""
        resp = client.get(
            "/api/v1/master/misi",
            params={"uni_id": uni_dk.id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(m["uni_id"] == uni_dk.id for m in data)

    def test_list_misi_empty_for_unknown_uni(self, client, uni_dk) -> None:
        """Unknown uni_id returns empty list (not 404)."""
        resp = client.get(
            "/api/v1/master/misi",
            params={"uni_id": 99999},
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestKategoriListEndpoint:
    """GET /api/v1/kategori/list — list active KategoriPemasukan for tenant."""

    def test_empty_list(self, client, bendahara_token, jemaat_a) -> None:
        """Tenant with no categories → empty array."""
        resp = client.get(
            "/api/v1/kategori/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/kategori/list")
        assert resp.status_code == 401

    def test_tenant_scoped(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        """Only own tenant's categories returned."""
        from app.models.kategori_pemasukan import KategoriPemasukan

        db = test_db()
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="Mine",
                alias="MIN",
                is_rutin=True,
                urutan=1,
            )
        )
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_b.id,
                nama="Other",
                alias="OTH",
                is_rutin=False,
                urutan=1,
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/kategori/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert any(item["nama"] == "Mine" for item in items)
        assert all(item["nama"] != "Other" for item in items)

    def test_excludes_inactive(self, client, bendahara_token, jemaat_a, test_db) -> None:
        """Only is_aktif=True categories returned."""
        from app.models.kategori_pemasukan import KategoriPemasukan

        db = test_db()
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="Active",
                alias="AC",
                is_aktif=True,
                urutan=1,
            )
        )
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="Inactive",
                alias="IN",
                is_aktif=False,
                urutan=2,
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/kategori/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["nama"] == "Active"

    def test_sorted_by_is_rutin_then_urutan(self, client, bendahara_token, jemaat_a, test_db) -> None:
        """Categories sorted: is_rutin DESC, urutan ASC, nama ASC."""
        from app.models.kategori_pemasukan import KategoriPemasukan

        db = test_db()
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="ZZZ-Rutin",
                alias="ZR",
                is_rutin=True,
                urutan=5,
            )
        )
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="AAA-NonRutin",
                alias="AN",
                is_rutin=False,
                urutan=1,
            )
        )
        db.add(
            KategoriPemasukan(
                tenant_id=jemaat_a.id,
                nama="BBB-Rutin-Prioritas",
                alias="BR",
                is_rutin=True,
                urutan=1,
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/kategori/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 3
        # is_rutin DESC first (BBB-Rutin-Prioritas urutan=1 wins), then non-rutin
        names = [item["nama"] for item in items]
        assert names[0] == "BBB-Rutin-Prioritas"  # rutin=True, urutan=1
        assert names[1] == "ZZZ-Rutin"  # rutin=True, urutan=5
        assert names[2] == "AAA-NonRutin"  # rutin=False
