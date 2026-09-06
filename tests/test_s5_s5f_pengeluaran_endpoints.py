"""
FASE 5 Sprint 5 — Integration tests for app/api/v1/pengeluaran.py.

Targets:
- GET  /api/v1/kategori-pengeluaran/list          (line 186)
- POST /api/v1/kategori-pengeluaran/create        (line 210)
- GET  /api/v1/pengeluaran/list                   (line 256)
- POST /api/v1/pengeluaran/create                 (line 285)

Subworkflow endpoints (submit/approve/reject) diluar scope Sprint 5 —
mereka panjang dan butuh state-machine + category fixture lebih dalam
(defer ke Sprint 6 ataucukup pengujian smoke script).
"""


class TestKategoriPengeluaranList:
    """GET /api/v1/kategori-pengeluaran/list — list active categories."""

    def test_empty_list(self, client, bendahara_token, jemaat_a) -> None:
        """Empty tenant returns empty array."""
        resp = client.get(
            "/api/v1/kategori-pengeluaran/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/kategori-pengeluaran/list")
        assert resp.status_code == 401

    def test_excludes_inactive(self, client, bendahara_token, jemaat_a, test_db) -> None:
        """Only is_aktif=True categories are returned."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran

        db = test_db()
        db.add(
            KategoriPengeluaran(
                tenant_id=jemaat_a.id,
                nama="Aktif",
                alias="AK",
                is_aktif=True,
                urutan=1,
            )
        )
        db.add(
            KategoriPengeluaran(
                tenant_id=jemaat_a.id,
                nama="NonAktif",
                alias="NA",
                is_aktif=False,
                urutan=2,
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/kategori-pengeluaran/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["nama"] == "Aktif"

    def test_tenant_scoped(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        """Bendahara only sees categories for their own tenant."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran

        db = test_db()
        db.add(
            KategoriPengeluaran(
                tenant_id=jemaat_a.id,
                nama="Mine",
                alias="MINE",
                is_aktif=True,
                urutan=1,
            )
        )
        db.add(
            KategoriPengeluaran(
                tenant_id=jemaat_b.id,
                nama="Other",
                alias="OTH",
                is_aktif=True,
                urutan=1,
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/kategori-pengeluaran/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        # Only tenant A's category
        assert all(item["nama"] != "Other" for item in items)


class TestKategoriPengeluaranCreate:
    """POST /api/v1/kategori-pengeluaran/create — BENDAHARA only."""

    def test_create_success(self, client, bendahara_token, jemaat_a) -> None:
        """BENDAHARA can create new category for their tenant."""
        resp = client.post(
            "/api/v1/kategori-pengeluaran/create",
            json={"nama": "Listrik", "alias": "LSTR", "is_rutin": True},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["nama"] == "Listrik"
        assert data["alias"] == "LSTR"
        assert data["is_rutin"] is True

    def test_create_duplicate_alias_409(self, client, bendahara_token, jemaat_a, test_db) -> None:
        """Duplicate alias in same tenant → 409."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran

        db = test_db()
        db.add(
            KategoriPengeluaran(
                tenant_id=jemaat_a.id,
                nama="Existing",
                alias="EXST",
                is_aktif=True,
                urutan=1,
            )
        )
        db.commit()
        db.close()
        resp = client.post(
            "/api/v1/kategori-pengeluaran/create",
            json={"nama": "New", "alias": "EXST", "is_rutin": False},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 409
        assert "EXST" in resp.json()["detail"]

    def test_create_requires_bendahara_role(self, client, ketua_token, jemaat_a) -> None:
        """KETUA_KEUANGAN cannot create (BENDAHARA only)."""
        resp = client.post(
            "/api/v1/kategori-pengeluaran/create",
            json={"nama": "Test", "alias": "TST", "is_rutin": False},
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        # Should be 403 (role-based deny) — not 201
        assert resp.status_code == 403

    def test_create_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.post(
            "/api/v1/kategori-pengeluaran/create",
            json={"nama": "Test", "alias": "TST", "is_rutin": False},
        )
        assert resp.status_code == 401

    def test_create_validation_nama_min_length(self, client, bendahara_token, jemaat_a) -> None:
        """nama < 2 chars → 422 validation error."""
        resp = client.post(
            "/api/v1/kategori-pengeluaran/create",
            json={"nama": "X", "alias": "TEST", "is_rutin": False},
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 422


class TestPengeluaranList:
    """GET /api/v1/pengeluaran/list — list expenses."""

    def test_empty_list(self, client, bendahara_token, jemaat_a) -> None:
        """Empty tenant → empty array."""
        resp = client.get(
            "/api/v1/pengeluaran/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_auth(self, client) -> None:
        """Unauthenticated → 401."""
        resp = client.get("/api/v1/pengeluaran/list")
        assert resp.status_code == 401

    def test_tenant_scoped(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        """Only own tenant's expenses visible."""
        from app.models.kategori_pengeluaran import KategoriPengeluaran
        from app.models.pengeluaran import Pengeluaran

        db = test_db()
        cat_a = KategoriPengeluaran(
            tenant_id=jemaat_a.id,
            nama="CatA",
            alias="CA",
            is_aktif=True,
            urutan=1,
        )
        cat_b = KategoriPengeluaran(
            tenant_id=jemaat_b.id,
            nama="CatB",
            alias="CB",
            is_aktif=True,
            urutan=1,
        )
        db.add_all([cat_a, cat_b])
        db.commit()
        db.refresh(cat_a)
        db.refresh(cat_b)
        db.add(
            Pengeluaran(
                tenant_id=jemaat_a.id,
                nomor_pengeluaran="P-001",
                kategori_pengeluaran_id=cat_a.id,
                jumlah=50000,
                tanggal="2026-08-22",
                tanggal_sabat="2026-08-22",
                id_rekap_mingguan="RK-TEST-A",
                status="approved",
            )
        )
        db.add(
            Pengeluaran(
                tenant_id=jemaat_b.id,
                nomor_pengeluaran="P-002",
                kategori_pengeluaran_id=cat_b.id,
                jumlah=75000,
                tanggal="2026-08-22",
                tanggal_sabat="2026-08-22",
                id_rekap_mingguan="RK-TEST-B",
                status="approved",
            )
        )
        db.commit()
        db.close()
        resp = client.get(
            "/api/v1/pengeluaran/list",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()
        # Only tenant A's expense
        assert all(item["nomor_pengeluaran"] != "P-002" for item in items)
        assert any(item["nomor_pengeluaran"] == "P-001" for item in items)
