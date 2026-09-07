"""
FASE 5 Sprint 8 — Integration tests untuk app/api/v1/m8_managed.py.

Covers:
- _generate_temp_password, _generate_username (pure helpers)
- POST /users/invite (Bendahara invite jemaat role)
- POST /kuitansi/{id}/void
- POST /pengeluaran/{id}/void
"""


from app.core.security import encrypt_pii


class TestGenerateTempPassword:
    def test_length_and_composition(self) -> None:
        from app.api.v1.m8_managed import _generate_temp_password

        pwd = _generate_temp_password()
        assert len(pwd) == 11  # 10 chars + '!'
        assert pwd.endswith("!")
        assert any(c.isupper() for c in pwd)
        assert any(c.islower() for c in pwd)
        assert any(c.isdigit() for c in pwd)

    def test_uniqueness_across_calls(self) -> None:
        from app.api.v1.m8_managed import _generate_temp_password

        seen = {_generate_temp_password() for _ in range(20)}
        assert len(seen) == 20


class TestGenerateUsername:
    def test_basic(self, test_db, jemaat_a) -> None:
        from app.api.v1.m8_managed import _generate_username

        username = _generate_username("BENDAHARA", "budi", test_db(), jemaat_a.id)
        assert username.startswith("bendahara_")
        assert "budi" in username

    def test_no_hint_uses_role_prefix(self, test_db, jemaat_a) -> None:
        from app.api.v1.m8_managed import _generate_username

        username = _generate_username("PENDETA", None, test_db(), jemaat_a.id)
        assert username.startswith("pendeta_")

    def test_ketua_keuangan_prefix(self, test_db, jemaat_a) -> None:
        from app.api.v1.m8_managed import _generate_username

        # role.replace('_keuangan', '') → 'ketua'
        username = _generate_username("KETUA_KEUANGAN", None, test_db(), jemaat_a.id)
        assert username.startswith("ketua_")


class TestInviteUser:
    def test_bendahara_invite_bendahara(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Bendahara Baru",
                "role": "BENDAHARA",
                "nomor_whatsapp": "081234567890",
                "username_hint": "bendahara_baru",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["role"] == "BENDAHARA"
        assert data["username"].startswith("bendahara_")
        assert data["password_plain"].endswith("!")
        assert data["tenant_id"] == jemaat_a.id

    def test_bendahara_invite_ketua(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Ketua Baru",
                "role": "KETUA_KEUANGAN",
                "nomor_whatsapp": "081234567891",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "KETUA_KEUANGAN"

    def test_phone_normalization(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Test WA",
                "role": "PENDETA",
                "nomor_whatsapp": "+62 812-3456-7892",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["nomor_whatsapp"] == "6281234567892"

    def test_duplicate_wa_conflict(self, client, bendahara_token, jemaat_a, bendahara_a) -> None:
        # bendahara_a sudah punya nomor_whatsapp=6281234567001
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Duplikat",
                "role": "BENDAHARA",
                "nomor_whatsapp": bendahara_a.nomor_whatsapp,
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 409

    def test_invalid_role(self, client, bendahara_token, jemaat_a) -> None:
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Test",
                "role": "SUPERADMIN",
                "nomor_whatsapp": "081234567893",
            },
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_ketua_cannot_invite(self, client, ketua_token, jemaat_a) -> None:
        """KETUA_KEUANGAN tidak boleh invite (jemaat role hanya Bendahara/Auditor)."""
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Test",
                "role": "BENDAHARA",
                "nomor_whatsapp": "081234567894",
            },
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client) -> None:
        resp = client.post(
            "/api/v1/users/invite",
            json={
                "nama_lengkap": "Test",
                "role": "BENDAHARA",
                "nomor_whatsapp": "081234567895",
            },
        )
        assert resp.status_code == 401


class TestVoidKuitansi:
    def _make_kuitansi(self, test_db, jemaat_a, status="draft"):
        from app.models.transaction import Kuitansi

        db = test_db()
        k = Kuitansi(
            tenant_id=jemaat_a.id,
            id_rekap_mingguan="RK-2026-09-05",
            nomor_kuitansi="001/NT/IX/26",
            tanggal_sabat="2026-09-05",
            nama_umat_encrypted=encrypt_pii("Budi"),
            perpuluhan_x_angka=100000,
            pt_angka=0,
            khusus_angka=0,
            total_pemberian_angka=100000,
            status=status,
            is_purged=False,
            created_via="web",
        )
        db.add(k)
        db.commit()
        db.refresh(k)
        db.close()
        return k

    def test_void_draft(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = self._make_kuitansi(test_db, jemaat_a, status="draft")
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "voided"
        assert resp.json()["entity_type"] == "kuitansi"

    def test_void_finalized_forbidden(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = self._make_kuitansi(test_db, jemaat_a, status="finalized")
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403

    def test_void_not_found(self, client, bendahara_token) -> None:
        resp = client.post(
            "/api/v1/kuitansi/999999/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_void_already_voided(self, client, bendahara_token, jemaat_a, test_db) -> None:
        k = self._make_kuitansi(test_db, jemaat_a, status="draft")
        client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 400

    def test_void_cross_tenant(self, client, bendahara_token, jemaat_a, jemaat_b, test_db) -> None:
        k = self._make_kuitansi(test_db, jemaat_b, status="draft")
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403

    def test_void_non_bendahara(self, client, ketua_token, jemaat_a, test_db) -> None:
        k = self._make_kuitansi(test_db, jemaat_a, status="draft")
        resp = client.post(
            f"/api/v1/kuitansi/{k.id}/void",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403


class TestVoidPengeluaran:
    def _make_pengeluaran(self, test_db, jemaat_a, status="draft"):
        from app.models.kategori_pengeluaran import KategoriPengeluaran
        from app.models.pengeluaran import Pengeluaran

        db = test_db()
        cat = KategoriPengeluaran(
            tenant_id=jemaat_a.id,
            nama="Listrik",
            alias="LST",
            is_aktif=True,
            urutan=1,
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
        p = Pengeluaran(
            tenant_id=jemaat_a.id,
            nomor_pengeluaran="P-001",
            kategori_pengeluaran_id=cat.id,
            jumlah=50000,
            tanggal="2026-09-05",
            tanggal_sabat="2026-09-05",
            id_rekap_mingguan="RK-2026-09-05",
            status=status,
            is_purged=False,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        db.close()
        return p

    def test_void_draft(self, client, bendahara_token, jemaat_a, test_db) -> None:
        p = self._make_pengeluaran(test_db, jemaat_a, status="draft")
        resp = client.post(
            f"/api/v1/pengeluaran/{p.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "pengeluaran"

    def test_void_approved_forbidden(self, client, bendahara_token, jemaat_a, test_db) -> None:
        p = self._make_pengeluaran(test_db, jemaat_a, status="approved")
        resp = client.post(
            f"/api/v1/pengeluaran/{p.id}/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 403

    def test_void_not_found(self, client, bendahara_token) -> None:
        resp = client.post(
            "/api/v1/pengeluaran/999999/void",
            headers={"Authorization": f"Bearer {bendahara_token}"},
        )
        assert resp.status_code == 404

    def test_void_non_bendahara(self, client, ketua_token, jemaat_a, test_db) -> None:
        p = self._make_pengeluaran(test_db, jemaat_a, status="draft")
        resp = client.post(
            f"/api/v1/pengeluaran/{p.id}/void",
            headers={"Authorization": f"Bearer {ketua_token}"},
        )
        assert resp.status_code == 403
