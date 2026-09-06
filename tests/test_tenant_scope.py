"""
FASE 4 Sprint 5 — Unit tests untuk app/core/tenant_scope.py.

**Scope:** Validate centralized tenant visibility resolver:
1. TenantScope dataclass (can_see, __contains__, frozen)
2. resolve_tenant_scope untuk 5 RBAC roles (happy paths)
3. resolve_tenant_scope boundary cases (orphan tenant, unknown role, dll)
4. Cross-tenant leakage prevention (ADMIN_UNI tidak bocor ke uni lain,
   AUDITOR_MISI tidak bocor ke misi lain)
5. tenant_filter helper (auto-filter via .in_())
6. assert_can_access guard (service-layer defense-in-depth)
7. require_tenant_scope dependency (FastAPI integration)

**Mengapa penting:** Ini adalah single source of truth untuk RBAC tenant
visibility. Kalau logika di sini salah, semua endpoint yang pakai
pattern `scope: TenantScope = Depends(require_tenant_scope)` akan
kompromi — termasuk kuitansi.py (S5-B) dan agregat.py (S5-C).

Test ini pure unit (tidak butuh HTTP) kecuali untuk require_tenant_scope
integration test di akhir.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from fastapi import HTTPException

from app.core.tenant_scope import (
    ALL_ROLES,
    ROLE_ADMIN_UNI,
    ROLE_AUDITOR_MISI,
    ROLE_JEMAAT_ONLY,
    TenantScope,
    assert_can_access,
    resolve_tenant_scope,
    tenant_filter,
)
from app.models.master import MisiKonferens, Uni
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User

# Import login helper dari conftest untuk integration tests
from tests.conftest import login

# ============================================================================
# 1. TenantScope dataclass
# ============================================================================

class TestTenantScopeDataclass:
    """Validasi dataclass immutable + helper methods."""

    def test_can_see_returns_true_for_visible_tenant(self):
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=5,
            visible_tenant_ids=[5],
        )
        assert scope.can_see(5) is True

    def test_can_see_returns_false_for_out_of_scope_tenant(self):
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=5,
            visible_tenant_ids=[5],
        )
        assert scope.can_see(99) is False

    def test_can_see_accepts_string_tenant_id_via_int_cast(self):
        """Biar aman kalau caller pakai string '5' (misal dari query param)."""
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=5,
            visible_tenant_ids=[5],
        )
        assert scope.can_see("5") is True  # type: ignore[arg-type]

    def test_contains_protocol_supports_in_operator(self):
        """`tenant_id in scope` shortcut."""
        scope = TenantScope(
            role="AUDITOR_MISI",
            primary_tenant_id=1,
            visible_tenant_ids=[1, 2, 3],
        )
        assert 2 in scope
        assert 99 not in scope

    def test_is_cross_tenant_false_for_jemaat_roles(self):
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=1,
            visible_tenant_ids=[1],
            is_cross_tenant=False,
        )
        assert scope.is_cross_tenant is False

    def test_is_cross_tenant_true_for_admin_auditor(self):
        scope = TenantScope(
            role="ADMIN_UNI",
            primary_tenant_id=1,
            visible_tenant_ids=[1, 2, 3],
            is_cross_tenant=True,
        )
        assert scope.is_cross_tenant is True

    def test_frozen_dataclass_rejects_mutation(self):
        """TenantScope HARUS immutable — defense against accidental state leak."""
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=5,
            visible_tenant_ids=[5],
        )
        with pytest.raises(FrozenInstanceError):
            scope.visible_tenant_ids = [99]  # type: ignore[misc]


# ============================================================================
# 2. resolve_tenant_scope — happy paths untuk 5 RBAC roles
# ============================================================================

class TestResolveHappyPaths:
    """Setiap role resolve ke scope yang sesuai expectation matrix."""

    def test_bendahara_sees_only_own_tenant(self, test_db, jemaat_a):
        db = test_db()
        current = {"id": 1, "role": "BENDAHARA", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.role == "BENDAHARA"
        assert scope.primary_tenant_id == jemaat_a.id
        assert scope.visible_tenant_ids == [jemaat_a.id]
        assert scope.is_cross_tenant is False

    def test_ketua_keuangan_sees_only_own_tenant(self, test_db, jemaat_a):
        db = test_db()
        current = {"id": 2, "role": "KETUA_KEUANGAN", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.role == "KETUA_KEUANGAN"
        assert scope.visible_tenant_ids == [jemaat_a.id]
        assert scope.is_cross_tenant is False

    def test_pendeta_sees_only_own_tenant(self, test_db, jemaat_a):
        db = test_db()
        current = {"id": 3, "role": "PENDETA", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.role == "PENDETA"
        assert scope.visible_tenant_ids == [jemaat_a.id]
        assert scope.is_cross_tenant is False

    def test_auditor_misi_sees_all_jemaat_in_same_misi(self, test_db, jemaat_a, jemaat_b):
        """Jemaat A dan B keduanya di misi_minahasa → keduanya visible."""
        db = test_db()
        current = {"id": 4, "role": "AUDITOR_MISI", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.role == "AUDITOR_MISI"
        assert scope.is_cross_tenant is True
        assert set(scope.visible_tenant_ids) == {jemaat_a.id, jemaat_b.id}

    def test_admin_uni_sees_all_jemaat_via_uni_chain(
        self, test_db, jemaat_a, jemaat_b, uni_dk, misi_minahasa
    ):
        """ADMIN_UNI traverse chain: nama_uni → Uni record → misi_ids → jemaat_ids."""
        db = test_db()
        current = {"id": 5, "role": "ADMIN_UNI", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.role == "ADMIN_UNI"
        assert scope.is_cross_tenant is True
        assert set(scope.visible_tenant_ids) == {jemaat_a.id, jemaat_b.id}


# ============================================================================
# 3. resolve_tenant_scope — boundary cases
# ============================================================================

class TestResolveBoundaryCases:
    """Edge cases: orphan tenant, unknown role, missing FK, dll."""

    def test_unknown_role_raises_value_error(self, test_db):
        """Programming error — seharusnya tidak terjadi kalau get_current_user
        filter role dengan benar. Tapi defense-in-depth: raise bukan silent."""
        db = test_db()
        current = {"id": 1, "role": "SUPERUSER", "tenant_id": 1}
        with pytest.raises(ValueError, match="role 'SUPERUSER' tidak dikenal"):
            resolve_tenant_scope(db, current)

    def test_primary_tenant_deleted_returns_empty_scope(self, test_db, jemaat_a):
        """Kalau Tenant record hilang dari DB, scope = [] (fail-closed)."""
        db = test_db()
        # Hapus jemaat_a
        db.delete(jemaat_a)
        db.commit()

        current = {"id": 1, "role": "BENDAHARA", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.primary_tenant_id is None
        assert scope.visible_tenant_ids == []

    def test_tenant_id_none_in_jwt_returns_empty_scope(self, test_db):
        """Edge case: tenant_id missing dari JWT claim (superadmin global?)."""
        db = test_db()
        current = {"id": 1, "role": "BENDAHARA", "tenant_id": None}
        scope = resolve_tenant_scope(db, current)

        assert scope.primary_tenant_id is None
        assert scope.visible_tenant_ids == []

    def test_auditor_misi_with_orphan_tenant_returns_empty_scope(
        self, test_db, uni_dk
    ):
        """AUDITOR_MISI tenant yang tidak punya misi_konferens_id → []."""
        db = test_db()
        # Tenant tanpa misi_konferens_id (orphan)
        from app.core.security import generate_tenant_signature
        orphan = Tenant(
            tenant_signature=generate_tenant_signature(
                uni_dk.nama_resmi, "Misi Orphan", "Jemaat Orphan"
            ),
            nama_uni=uni_dk.nama_resmi,
            nama_kantor_misi="Misi Orphan",
            nama_jemaat_lokal="Jemaat Orphan",
            initial_jemaat="OR",
            slug="jemaat-orphan",
            status="active",
            plan="free",
            misi_konferens_id=None,  # ORPHAN
        )
        db.add(orphan)
        db.commit()
        db.refresh(orphan)

        current = {"id": 1, "role": "AUDITOR_MISI", "tenant_id": orphan.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.visible_tenant_ids == []

    def test_admin_uni_with_legacy_tenant_returns_empty_scope(
        self, test_db, uni_dk
    ):
        """ADMIN_UNI tenant dengan nama_uni yang tidak match tabel Uni → []."""
        db = test_db()
        from app.core.security import generate_tenant_signature
        legacy = Tenant(
            tenant_signature=generate_tenant_signature(
                "Uni Legacy Tidak Terdaftar", "Misi X", "Jemaat Y"
            ),
            nama_uni="Uni Legacy Tidak Terdaftar",  # NOT in Uni table
            nama_kantor_misi="Misi X",
            nama_jemaat_lokal="Jemaat Y",
            initial_jemaat="LX",
            slug="jemaat-legacy",
            status="active",
            plan="free",
            misi_konferens_id=None,
        )
        db.add(legacy)
        db.commit()
        db.refresh(legacy)

        current = {"id": 1, "role": "ADMIN_UNI", "tenant_id": legacy.id}
        scope = resolve_tenant_scope(db, current)

        assert scope.visible_tenant_ids == []

    def test_admin_uni_with_uni_having_no_misi_returns_empty_scope(
        self, test_db, uni_dk
    ):
        """ADMIN_UNI Uni record ada tapi tidak ada misi di bawahnya → []."""
        db = test_db()
        # Buat Uni baru TANPA misi sama sekali
        empty_uni = Uni(nama_resmi="Uni Empty NoMisi", kode="UENM")
        db.add(empty_uni)
        db.commit()
        db.refresh(empty_uni)

        # Buat tenant di Uni kosong ini (bukan reuse jemaat_a supaya isolated)
        from app.core.security import generate_tenant_signature
        tenant_empty = Tenant(
            tenant_signature=generate_tenant_signature(
                "Uni Empty NoMisi", "Misi X", "Jemaat Y"
            ),
            nama_uni="Uni Empty NoMisi",
            nama_kantor_misi="Misi X",
            nama_jemaat_lokal="Jemaat Y",
            initial_jemaat="YE",
            slug="jemaat-empty-uni",
            status="active",
            plan="free",
            misi_konferens_id=None,
        )
        db.add(tenant_empty)
        db.commit()
        db.refresh(tenant_empty)

        current = {"id": 1, "role": "ADMIN_UNI", "tenant_id": tenant_empty.id}
        scope = resolve_tenant_scope(db, current)

        # Uni record ketemu (Uni Empty NoMisi), tapi tidak ada misi di bawahnya → []
        assert scope.visible_tenant_ids == []


# ============================================================================
# 4. Cross-tenant leakage prevention — security tests
# ============================================================================

class TestCrossTenantLeakage:
    """Critical: pastikan ADMIN_UNI dan AUDITOR_MISI TIDAK bocor ke scope lain."""

    def test_admin_uni_does_not_see_other_uni_jemaat(
        self, test_db, jemaat_a, jemaat_b, uni_dk, misi_minahasa
    ):
        """ADMIN_UNI di UKIKT tidak boleh lihat jemaat dari uni lain."""
        db = test_db()
        # Buat uni kedua dengan jemaat di bawahnya
        uni_x = Uni(nama_resmi="Uni X (Lain)", kode="UXX")
        db.add(uni_x)
        db.commit()
        db.refresh(uni_x)

        misi_x = MisiKonferens(
            nama_resmi="Misi X",
            kode="MX",
            uni_id=uni_x.id,
            jenis="MISI",
        )
        db.add(misi_x)
        db.commit()
        db.refresh(misi_x)

        from app.core.security import generate_tenant_signature
        jemaat_x = Tenant(
            tenant_signature=generate_tenant_signature(
                "Uni X (Lain)", "Misi X", "Jemaat X"
            ),
            nama_uni="Uni X (Lain)",
            nama_kantor_misi="Misi X",
            nama_jemaat_lokal="Jemaat X",
            initial_jemaat="JX",
            slug="jemaat-x",
            status="active",
            plan="free",
            misi_konferens_id=misi_x.id,
        )
        db.add(jemaat_x)
        db.commit()
        db.refresh(jemaat_x)

        # ADMIN_UNI di jemaat_a (UKIKT)
        current = {"id": 1, "role": "ADMIN_UNI", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        # Harus видит jemaat_a dan jemaat_b (UKIKT), TIDAK jemaat_x
        assert jemaat_a.id in scope.visible_tenant_ids
        assert jemaat_b.id in scope.visible_tenant_ids
        assert jemaat_x.id not in scope.visible_tenant_ids

    def test_auditor_misi_does_not_see_other_misi_jemaat(
        self, test_db, jemaat_a, uni_dk
    ):
        """AUDITOR_MISI di misi_minahasa tidak boleh lihat jemaat dari misi lain."""
        db = test_db()
        # Buat misi kedua (uni sama, misi beda) dengan jemaat
        uni2 = Uni(nama_resmi="UKIKT", kode="UKIKT2")
        # (pakai nama_resmi sama biar di Uni table cuma 1 row, tapi kita
        #  test case dimana ada 2 Uni records beda kode)
        # Actually mari buat Uni kedua dengan kode beda
        db.add(uni2)
        db.commit()
        db.refresh(uni2)

        misi_lain = MisiKonferens(
            nama_resmi="Misi Lain",
            kode="ML",
            uni_id=uni2.id,
            jenis="MISI",
        )
        db.add(misi_lain)
        db.commit()
        db.refresh(misi_lain)

        from app.core.security import generate_tenant_signature
        jemaat_lain = Tenant(
            tenant_signature=generate_tenant_signature(
                "UKIKT", "Misi Lain", "Jemaat Lain"
            ),
            nama_uni="UKIKT",
            nama_kantor_misi="Misi Lain",
            nama_jemaat_lokal="Jemaat Lain",
            initial_jemaat="JL",
            slug="jemaat-lain",
            status="active",
            plan="free",
            misi_konferens_id=misi_lain.id,
        )
        db.add(jemaat_lain)
        db.commit()
        db.refresh(jemaat_lain)

        # AUDITOR_MISI di jemaat_a (misi_minahasa)
        current = {"id": 1, "role": "AUDITOR_MISI", "tenant_id": jemaat_a.id}
        scope = resolve_tenant_scope(db, current)

        # Hanya jemaat_a dan jemaat_b (sama misi_minahasa), TIDAK jemaat_lain
        assert jemaat_a.id in scope.visible_tenant_ids
        assert jemaat_lain.id not in scope.visible_tenant_ids


# ============================================================================
# 5. tenant_filter helper
# ============================================================================

class TestTenantFilterHelper:
    """Helper untuk auto-apply `WHERE tenant_id IN (...)` ke query."""

    def test_tenant_filter_applies_in_clause(self, test_db, jemaat_a, jemaat_b, create_kuitansi):
        """Pastikan helper apply `model.tenant_id.in_(scope.visible_tenant_ids)`."""
        # Setup: 2 kuitansi, satu di jemaat_a, satu di jemaat_b
        create_kuitansi(tenant_id=jemaat_a.id)
        create_kuitansi(tenant_id=jemaat_b.id)

        db = test_db()
        # BENDAHARA jemaat_a — hanya boleh lihat jemaat_a
        scope_a = resolve_tenant_scope(
            db, {"id": 1, "role": "BENDAHARA", "tenant_id": jemaat_a.id}
        )
        q = tenant_filter(db.query(Kuitansi), Kuitansi, scope_a)
        results = q.all()

        assert len(results) == 1
        assert results[0].tenant_id == jemaat_a.id

    def test_tenant_filter_raises_for_model_without_tenant_id(self, test_db, jemaat_a):
        """Kalau model tidak punya kolom tenant_id, raise AttributeError
        (bukan silent pass — programmer error harus surfaced)."""

        class FakeModelNoTenantId:
            """Stub model tanpa tenant_id column."""

        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=jemaat_a.id,
            visible_tenant_ids=[jemaat_a.id],
        )

        with pytest.raises(AttributeError, match="tidak punya kolom 'tenant_id'"):
            tenant_filter(test_db().query(Kuitansi), FakeModelNoTenantId, scope)


# ============================================================================
# 6. assert_can_access guard
# ============================================================================

class TestAssertCanAccess:
    """Hard guard untuk service layer (defense-in-depth)."""

    def test_no_raises_for_visible_tenant(self, test_db, jemaat_a):
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=jemaat_a.id,
            visible_tenant_ids=[jemaat_a.id],
        )
        # Should not raise
        assert_can_access(scope, jemaat_a.id)

    def test_raises_403_for_out_of_scope_tenant(self, test_db, jemaat_a, jemaat_b):
        """Cross-tenant access attempt → HTTPException 403."""
        scope = TenantScope(
            role="BENDAHARA",
            primary_tenant_id=jemaat_a.id,
            visible_tenant_ids=[jemaat_a.id],
        )
        with pytest.raises(HTTPException) as exc_info:
            assert_can_access(scope, jemaat_b.id)
        assert exc_info.value.status_code == 403
        assert "tidak ada dalam scope" in str(exc_info.value.detail)


# ============================================================================
# 7. require_tenant_scope FastAPI dependency (integration)
# ============================================================================

class TestRequireTenantScopeDependency:
    """Integration test — require_tenant_scope dipanggil via FastAPI Depends()."""

    def test_returns_scope_when_visible_non_empty(
        self, test_db, jemaat_a, bendahara_a, client
    ):
        """Login sebagai BENDAHARA → require_tenant_scope return scope.

        Catatan: bendahara_a fixture HARUS diminta supaya user BENDAHARA
        dibuat di DB test (lihat conftest.py:175). Tanpa fixture ini,
        user tidak ada → login 401.
        """
        resp = login(client, "bendahara", "Bendahara123!")
        assert resp.status_code == 200, resp.text

        # Panggil endpoint yang pakai require_tenant_scope (search kuitansi)
        token = resp.json()["access_token"]
        list_resp = client.get(
            "/api/v1/kuitansi/search?limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 200 OK (dengan empty results karena DB bersih)
        assert list_resp.status_code == 200

    def test_raises_403_when_tenant_orphan_auditor_misi(
        self, test_db, uni_dk, client
    ):
        """AUDITOR_MISI user dibuat dengan tenant_id orphan (no misi_konferens_id)
        → require_tenant_scope harus raise 403 (bukan return empty list)."""
        db = test_db()
        from app.core.security import generate_tenant_signature, hash_password

        # Buat orphan tenant (no misi_konferens_id)
        orphan = Tenant(
            tenant_signature=generate_tenant_signature(
                uni_dk.nama_resmi, "Misi Orphan", "Jemaat Orphan"
            ),
            nama_uni=uni_dk.nama_resmi,
            nama_kantor_misi="Misi Orphan",
            nama_jemaat_lokal="Jemaat Orphan",
            initial_jemaat="OR",
            slug="jemaat-orphan-2",
            status="active",
            plan="free",
            misi_konferens_id=None,
        )
        db.add(orphan)
        db.commit()
        db.refresh(orphan)

        # Buat AUDITOR_MISI user di orphan tenant
        auditor_orphan = User(
            username="auditor_orphan",
            nama_lengkap="Auditor Orphan",
            password_hash=hash_password("AuditOrphan123!"),
            role="AUDITOR_MISI",
            tenant_id=orphan.id,
            is_active=True,
        )
        db.add(auditor_orphan)
        db.commit()
        db.close()

        # Login sebagai auditor_orphan
        resp = login(client, "auditor_orphan", "AuditOrphan123!")
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        # Panggil endpoint yang pakai require_tenant_scope (kuitansi/search)
        list_resp = client.get(
            "/api/v1/kuitansi/search?limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        # 403 karena scope kosong (orphan → no visible tenants)
        assert list_resp.status_code == 403
        assert "scope kosong" in list_resp.json().get("detail", "").lower() or \
               "scope kosong" in str(list_resp.json()).lower()


# ============================================================================
# 8. Constants sanity
# ============================================================================

class TestRoleConstants:
    """Validasi konstanta role (jangan typo / drift dari master list)."""

    def test_all_roles_includes_5_rbac_roles(self):
        assert ALL_ROLES == {"BENDAHARA", "KETUA_KEUANGAN", "PENDETA", "AUDITOR_MISI", "ADMIN_UNI"}

    def test_role_jemaat_only_has_3_single_tenant_roles(self):
        assert ROLE_JEMAAT_ONLY == {"BENDAHARA", "KETUA_KEUANGAN", "PENDETA"}

    def test_role_auditor_misi_and_admin_uni_are_cross_tenant(self):
        # Cross-tenant roles
        assert ROLE_AUDITOR_MISI == "AUDITOR_MISI"
        assert ROLE_ADMIN_UNI == "ADMIN_UNI"

    def test_no_overlap_between_jemaat_only_and_cross_tenant(self):
        """Sanity: jemaat-only roles TIDAK masuk cross-tenant set."""
        cross = {ROLE_AUDITOR_MISI, ROLE_ADMIN_UNI}
        assert ROLE_JEMAAT_ONLY.isdisjoint(cross)
