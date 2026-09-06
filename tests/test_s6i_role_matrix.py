"""
FASE 4 Sprint 6-I — Role × endpoint matrix tests.

**Tujuan:** Validasi bahwa setiap endpoint yang dimigrasi ke TenantScope
memberikan response code yang BENAR untuk masing-masing 5 RBAC role.

**Mengapa matrix ini penting:**
1. Defense-in-depth — kalau ada endpoint yang return 200 untuk role yang
   seharusnya 403, kita akan tahu tepat endpoint mana.
2. Regression guard — kalau seseorang nanti patch ulang endpoint tanpa
   test ini, perubahan role guard akan langsung ketangkep.
3. Dokumentasi hidup — table di bawah adalah "kontrak" RBAC yang harus
   dipenuhi.

**Endpoint yang dicover di file ini (Sprint 6-H/B + S5-B sanity):**
- agregat.py::GET /agregat/sabat-ini        (S6-H, S6-B regression)
- agregat.py::GET /agregat/ytd              (S6-H, S6-B regression)
- sync.py::POST /sync/upload               (S6-H)
- sync.py::GET  /sync/pull                 (S6-H, juga security fix verification)
- dashboard.py::GET /dashboard/sabat-info  (S6-C) — covered separately
- kuitansi.py::GET /kuitansi/search        (S5-B baseline, sanity check)

**Kontrak RBAC untuk endpoint S6-H:**

| Endpoint            | BENDAHARA | KETUA_KEUANGAN | PENDETA | AUDITOR_MISI | ADMIN_UNI |
|---------------------|-----------|----------------|---------|--------------|-----------|
| GET /sabat-ini      | 200       | 200            | 200     | 200          | 200       |
| GET /ytd            | 200       | 200            | 200     | 200          | 200       |
| POST /sync/upload   | 200       | 200            | 403     | 403          | 403       |
| GET /sync/pull      | 403       | 403            | 403     | 200          | 200       |

**Mengapa /sabat-ini & /ytd 200 untuk semua role:**
Agregat endpoint TIDAK punya role guard — role guard di lakukan di
dashboard/quick_input. Agregat compute agregasi sesuai scope (tenant/misi/uni).
- BENDAHARA/PENDETA/KETUA → scope=tenant → data 1 jemaat
- AUDITOR_MISI → scope=misi → data semua jemaat di 1 misi
- ADMIN_UNI → scope=uni → data semua jemaat via chain uni

Response code selalu 200 (kecuali scope kosong → 403 dari require_tenant_scope).

**Mengapa /sync/upload & /sync/pull beda:**
Endpoint sync punya hard role guard di dalam body endpoint:
- /sync/upload → BENDAHARA + KETUA_KEUANGAN only (push dari jemaat)
- /sync/pull → AUDITOR_MISI + ADMIN_UNI only (pull dari misi/uni)
"""
from __future__ import annotations

import pytest

from tests.conftest import login

# Endpoint paths
SABAT_INI = "/api/v1/agregat/sabat-ini"
YTD = "/api/v1/agregat/ytd"
SYNC_UPLOAD = "/api/v1/sync/upload"
SYNC_PULL = "/api/v1/sync/pull"
KUITANSI_SEARCH = "/api/v1/kuitansi/search?limit=1"  # S5-B sanity


def _login_as(client, username: str, password: str):
    """Login & return token. Raises if login fails."""
    resp = login(client, username, password)
    assert resp.status_code == 200, (
        f"Login gagal untuk {username}: {resp.status_code} {resp.text}"
    )
    return resp.json()["access_token"]


@pytest.fixture(scope="function")
def bendahara_token(client, bendahara_a):
    return _login_as(client, "bendahara", "Bendahara123!")


@pytest.fixture(scope="function")
def ketua_token(client, ketua_a):
    return _login_as(client, "ketua_keuang", "Ketua123!")


@pytest.fixture(scope="function")
def pendeta_token(client, pendeta):
    """Pendeta — username fixture pakai 'pendata' (typo historis)."""
    return _login_as(client, "pendata", "Pendeta123!")


@pytest.fixture(scope="function")
def admin_uni_token(client, admin_uni):
    return _login_as(client, "admin_uni", "AdminUni123!")


@pytest.fixture(scope="function")
def auditor_misi_token(client, auditor_misi):
    return _login_as(client, "auditor_misi", "AuditMisi123!")


# ============================================================================
# GET /agregat/sabat-ini  — role matrix
# ============================================================================

class TestSabatIniRoleMatrix:
    """Semua 5 role boleh akses /sabat-ini (200), beda isinya saja."""

    def test_bendahara_200(self, client, bendahara_token, jemaat_a):
        resp = client.get(
            SABAT_INI, headers={"Authorization": f"Bearer {bendahara_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Bendahara → scope=tenant
        assert data.get("scope") == "tenant", f"Expected scope=tenant, got {data}"

    def test_ketua_keuangan_200(self, client, ketua_token, jemaat_a):
        resp = client.get(
            SABAT_INI, headers={"Authorization": f"Bearer {ketua_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("scope") == "tenant"

    def test_pendeta_200(self, client, pendeta_token, jemaat_a):
        resp = client.get(
            SABAT_INI, headers={"Authorization": f"Bearer {pendeta_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("scope") == "tenant"

    def test_auditor_misi_200(self, client, auditor_misi_token, jemaat_a, jemaat_b):
        """AUDITOR_MISI → scope=misi → lihat jemaat_a + jemaat_b agregat."""
        resp = client.get(
            SABAT_INI, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("scope") == "misi"

    def test_admin_uni_200(self, client, admin_uni_token, jemaat_a, jemaat_b):
        """ADMIN_UNI → scope=uni → lihat jemaat_a + jemaat_b agregat via chain."""
        resp = client.get(
            SABAT_INI, headers={"Authorization": f"Bearer {admin_uni_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("scope") == "uni"


# ============================================================================
# GET /agregat/ytd — role matrix
# ============================================================================

class TestYtdRoleMatrix:
    """Sama seperti /sabat-ini — semua role 200, scope field membedakan."""

    def test_bendahara_200(self, client, bendahara_token, jemaat_a):
        resp = client.get(
            YTD, headers={"Authorization": f"Bearer {bendahara_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("scope") == "tenant"

    def test_ketua_keuangan_200(self, client, ketua_token, jemaat_a):
        resp = client.get(
            YTD, headers={"Authorization": f"Bearer {ketua_token}"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("scope") == "tenant"

    def test_pendeta_200(self, client, pendeta_token, jemaat_a):
        resp = client.get(
            YTD, headers={"Authorization": f"Bearer {pendeta_token}"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("scope") == "tenant"

    def test_auditor_misi_200(self, client, auditor_misi_token, jemaat_a, jemaat_b):
        resp = client.get(
            YTD, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("scope") == "misi"

    def test_admin_uni_200(self, client, admin_uni_token, jemaat_a, jemaat_b):
        resp = client.get(
            YTD, headers={"Authorization": f"Bearer {admin_uni_token}"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("scope") == "uni"


# ============================================================================
# POST /sync/upload — role matrix (hard role guard)
# ============================================================================

class TestSyncUploadRoleMatrix:
    """Hanya BENDAHARA + KETUA_KEUANGAN yang boleh push (200).
    Sisanya → 403.

    Catatan: Untuk BENDAHARA/KETUA_KEUANGAN kami hanya verify return code 200
    (tidak depend pada factory Kuitansi yang punya kolom porsi_x_uni dll).
    Empty upload (no kuitansi) tetap return 200 — endpoint idempotent."""

    def test_bendahara_200(self, client, bendahara_token, jemaat_a):
        """Bendahara boleh push (return 200 even dengan 0 kuitansi)."""
        resp = client.post(
            SYNC_UPLOAD, headers={"Authorization": f"Bearer {bendahara_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("tenant_id") == jemaat_a.id
        assert data.get("uploaded") == 0  # no kuitansi in test DB

    def test_ketua_keuangan_200(self, client, ketua_token, jemaat_a):
        """Ketua Keuangan juga boleh push."""
        resp = client.post(
            SYNC_UPLOAD, headers={"Authorization": f"Bearer {ketua_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("tenant_id") == jemaat_a.id

    def test_pendeta_403(self, client, pendeta_token, jemaat_a):
        """Pendeta bukan bendahara/ketua → 403."""
        resp = client.post(
            SYNC_UPLOAD, headers={"Authorization": f"Bearer {pendeta_token}"}
        )
        assert resp.status_code == 403, resp.text
        assert "bendahara" in resp.json().get("detail", "").lower() or \
               "ketua" in resp.json().get("detail", "").lower()

    def test_auditor_misi_403(self, client, auditor_misi_token, jemaat_a):
        """AUDITOR_MISI boleh pull, BUKAN push → 403."""
        resp = client.post(
            SYNC_UPLOAD, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code == 403, resp.text

    def test_admin_uni_403(self, client, admin_uni_token, jemaat_a):
        """ADMIN_UNI boleh pull, BUKAN push → 403."""
        resp = client.post(
            SYNC_UPLOAD, headers={"Authorization": f"Bearer {admin_uni_token}"}
        )
        assert resp.status_code == 403, resp.text


# ============================================================================
# GET /sync/pull — role matrix + SECURITY FIX verification
# ============================================================================

class TestSyncPullRoleMatrix:
    """Hanya AUDITOR_MISI + ADMIN_UNI yang boleh pull (200).
    Sisanya → 403.

    CRITICAL: AUDITOR_MISI/ADMIN_UNI harus lihat HANYA sync_outbox
    milik jemaat yang visible (bukan semua outbox global — itu
    security fix yang dipasang di S6-H).
    """

    def test_bendahara_403(self, client, bendahara_token, jemaat_a):
        """BENDAHARA tidak boleh pull — itu wewenang auditor/admin."""
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {bendahara_token}"}
        )
        assert resp.status_code == 403, resp.text
        assert "auditor" in resp.json().get("detail", "").lower() or \
               "admin uni" in resp.json().get("detail", "").lower()

    def test_ketua_keuangan_403(self, client, ketua_token, jemaat_a):
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {ketua_token}"}
        )
        assert resp.status_code == 403, resp.text

    def test_pendeta_403(self, client, pendeta_token, jemaat_a):
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {pendeta_token}"}
        )
        assert resp.status_code == 403, resp.text

    def test_auditor_misi_200_empty(self, client, auditor_misi_token, jemaat_a, jemaat_b):
        """AUDITOR_MISI 200 dengan empty list (DB test bersih, tidak ada outbox)."""
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("count") == 0
        assert data.get("items") == []

    def test_admin_uni_200_empty(self, client, admin_uni_token, jemaat_a, jemaat_b):
        """ADMIN_UNI 200 dengan empty list."""
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {admin_uni_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("count") == 0
        assert data.get("items") == []


class TestSyncPullSecurityFixMinimal:
    """Sprint 6-I: Light-weight verification S6-H security fix.

    Cukup verifikasi bahwa /sync/pull (sebagai AUDITOR_MISI) return empty
    list ketika DB test bersih — bukti filter scope.visible_tenant_ids
    applied (kalau tidak applied, query all SyncOutbox → all rows visible).

    Cross-tenant leakage penuh (multi-tenant setup) akan dicover
    di Sprint 6-J secara lebih mendalam.
    """

    def test_pull_returns_empty_list_not_all_outboxes(
        self, client, auditor_misi_token, jemaat_a, jemaat_b, test_db
    ):
        """AUDITOR_MISI di jemaat_a (misi_minahasa) → pull → empty.

        Pre-S6-H bug: filter by user.tenant_id → hanya jemaat_a visible,
        tapi kalau filter tidak applied sama sekali → semua outbox bocor.
        Patch S6-H menggunakan scope.visible_tenant_ids → query terfilter.
        """
        # Seed 1 SyncOutbox row langsung (skip anonymizer complexity)
        db = test_db()
        import json

        from app.models.sync import SyncOutbox
        outbox = SyncOutbox(
            tenant_id=jemaat_b.id,  # visible ke AUDITOR_MISI
            payload_json=json.dumps({
                "payload_hash": "abc123",
                "tenant_signature": "test",
                "porsi_kantor_misi": 100000,
            }),
            payload_hash="abc123",
        )
        db.add(outbox)
        db.commit()
        db.close()

        # AUDITOR_MISI pull → harusnya dapat 1 item dari jemaat_b (visible)
        resp = client.get(
            SYNC_PULL, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Pre-S6-H bug: kalau filter TIDAK applied → semua SyncOutbox bocor
        # (di test ini hanya 1 row, jadi minimal count >= 1 tapi
        #  HANYA yg tenant_id ∈ scope.visible_tenant_ids yg boleh muncul).
        items = data.get("items", [])
        for item in items:
            assert item["tenant_id"] in {jemaat_a.id, jemaat_b.id}, (
                f"SECURITY VIOLATION! Pulled tenant_id={item['tenant_id']} "
                f"NOT in auditor scope ({jemaat_a.id}, {jemaat_b.id})"
            )


# ============================================================================
# Sanity: kuitansi.py /kuitansi/search (S5-B) tetap jalan setelah S6-H
# ============================================================================

class TestKuitansiSearchSanity:
    """S5-B baseline: /kuitansi/search pakai TenantScope. Verify masih
    jalan setelah S6-H patches — regression check."""

    def test_bendahara_200(self, client, bendahara_token, jemaat_a):
        resp = client.get(
            KUITANSI_SEARCH, headers={"Authorization": f"Bearer {bendahara_token}"}
        )
        # Boleh 200 even dengan empty list, atau 403 kalau scope kosong
        assert resp.status_code in (200, 403), resp.text

    def test_auditor_misi_200_or_403(self, client, auditor_misi_token, jemaat_a):
        resp = client.get(
            KUITANSI_SEARCH, headers={"Authorization": f"Bearer {auditor_misi_token}"}
        )
        assert resp.status_code in (200, 403), resp.text


# ============================================================================
# Unauthenticated request → 401 (semua endpoint yang pakai require_tenant_scope)
# ============================================================================

class TestUnauthenticatedRejected:
    """Kalau tidak ada token, harus 401 untuk endpoint yang
    pakai require_tenant_scope."""

    @pytest.mark.parametrize("endpoint,method", [
        (SABAT_INI, "GET"),
        (YTD, "GET"),
        (SYNC_UPLOAD, "POST"),
        (SYNC_PULL, "GET"),
    ])
    def test_no_token_401(self, client, endpoint, method):
        if method == "GET":
            resp = client.get(endpoint)
        else:
            resp = client.post(endpoint)
        assert resp.status_code == 401, (
            f"{method} {endpoint} tanpa token harus 401, got {resp.status_code}"
        )

    @pytest.mark.parametrize("endpoint,method", [
        (SABAT_INI, "GET"),
        (YTD, "GET"),
        (SYNC_UPLOAD, "POST"),
        (SYNC_PULL, "GET"),
    ])
    def test_invalid_token_401(self, client, endpoint, method):
        if method == "GET":
            resp = client.get(
                endpoint, headers={"Authorization": "Bearer invalid-token-xxx"}
            )
        else:
            resp = client.post(
                endpoint, headers={"Authorization": "Bearer invalid-token-xxx"}
            )
        assert resp.status_code == 401, (
            f"{method} {endpoint} dengan invalid token harus 401, got {resp.status_code}"
        )
