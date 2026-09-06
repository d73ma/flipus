"""
FASE 4 Sprint 6-J — Cross-tenant leakage test per migrated endpoint.

Verifikasi bahwa tenant A tidak bisa melihat data tenant B lewat endpoint
yang sudah dimigrasi ke TenantScope (S6B/C). Tujuan: regression guard
untuk multi-tenant data isolation di production.

Strategi:
- Seed kuitansi BERBEDA di 2 jemaat (jemaat_a, jemaat_b) yang keduanya
  bernaung di misi_minahasa yang sama.
- Login sebagai BENDAHARA jemaat_a (single-tenant role — scope = [a.id]).
- Hit endpoint → assert HANYA data jemaat_a yang muncul, TIDAK ada
  data jemaat_b (nomor_kuitansi, tenant_id, nama_jemaat "Timur B").
- Cross-misi: bikin misi_lain (unattached ke uni_dk) → AUDITOR_MISI
  jemaat_a tidak boleh lihat jemaat_c di misi_lain.

Endpoints tested:
- GET /api/v1/agregat/sabat-ini       (S6C dashboard)
- GET /api/v1/agregat/ytd              (S6C dashboard)
- POST /api/v1/sync/upload            (S6H sync, hard role guard)
- GET /api/v1/sync/pull               (S6H security fix — critical)
- GET /api/v1/kuitansi/search         (S5B baseline)

Cross-cutting:
- BENDAHARA jemaat_a → tidak boleh lihat jemaat_b
- AUDITOR_MISI jemaat_a → hanya jemaat di misi_minahasa (a, b), BUKAN misi_lain (c)
- ADMIN_UNI → jemaat di uni_dk (a, b, c_jemaat_lain_di_uni_dk) tapi BUKAN jemaat di uni_lain

Skema alokasi tenant:
  uni_dk
    ├─ misi_minahasa
    │   ├─ jemaat_a (BENDAHARA_A)
    │   └─ jemaat_b
    └─ misi_lain
        └─ jemaat_c
  uni_lain
    └─ misi_x
        └─ jemaat_d (cross-uni leakage target)
"""
import os

import pytest

# Set test env BEFORE importing app
os.environ["DATABASE_URL_LOCAL"] = "sqlite:///./test_flipus_t25.db"
os.environ["SECRET_KEY"] = "test-secret-key-t25-do-not-use-in-prod"
os.environ["PII_ENCRYPTION_KEY"] = "WW7LHfY_bmiNjXAiTZjmHI4w_wwPQH-_x9U722_FCDY="
os.environ["LICENSE_TENANT_SIGNATURE_SALT"] = "test-salt-t25"

from app.core.security import generate_tenant_signature, hash_password
from app.models.master import MisiKonferens, PersentaseConfig, Uni
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User
from app.utils.sabat_counter import get_sabat_info

# ===== Helper: extra domain fixtures =====

@pytest.fixture(scope="function")
def uni_lain(test_db):
    """Uni kedua untuk cross-uni leakage test."""
    db = test_db()
    uni = Uni(nama_resmi="GMAHK UKIKT Barat", kode="UKIKT_B")
    db.add(uni)
    db.commit()
    db.refresh(uni)
    db.close()
    return uni


@pytest.fixture(scope="function")
def misi_lain(test_db, uni_lain):
    """Misi di uni_lain — visible only untuk ADMIN_UNI uni_lain."""
    db = test_db()
    misi = MisiKonferens(
        nama_resmi="Misi DK Sulut Barat",
        kode="DK.SULBAR",
        uni_id=uni_lain.id,
        jenis="MISI",
    )
    db.add(misi)
    db.commit()
    db.refresh(misi)
    # pct config (avoid crash on pct lookups)
    db.add(PersentaseConfig(
        scope="MISI",
        ref_id=misi.id,
        pct_x_jemaat=1.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.0,
    ))
    db.commit()
    db.close()
    return misi


@pytest.fixture(scope="function")
def jemaat_c(test_db, uni_dk, misi_lain):
    """Jemaat di misi_lain (tetap di uni_dk) — uji auditor_misi isolation."""
    db = test_db()
    nama = "Jemaat Sulut Barat"
    t = Tenant(
        tenant_signature=generate_tenant_signature(
            uni_dk.nama_resmi, misi_lain.nama_resmi, nama
        ),
        nama_uni=uni_dk.nama_resmi,
        nama_kantor_misi=misi_lain.nama_resmi,
        nama_jemaat_lokal=nama,
        initial_jemaat="SW",
        slug="jemaat-sulut-barat",
        status="active",
        plan="free",
        misi_konferens_id=misi_lain.id,  # attached to misi_lain, NOT misi_minahasa
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    db.close()
    return t


@pytest.fixture(scope="function")
def jemaat_d(test_db, uni_lain, misi_lain):
    """Jemaat di uni_lain — uji ADMIN_UNI cross-uni isolation."""
    db = test_db()
    nama = "Jemaat Manado Utara"
    t = Tenant(
        tenant_signature=generate_tenant_signature(
            uni_lain.nama_resmi, misi_lain.nama_resmi, nama
        ),
        nama_uni=uni_lain.nama_resmi,
        nama_kantor_misi=misi_lain.nama_resmi,
        nama_jemaat_lokal=nama,
        initial_jemaat="MU",
        slug="jemaat-manado-utara",
        status="active",
        plan="free",
        misi_konferens_id=misi_lain.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    db.close()
    return t


@pytest.fixture(scope="function")
def kuitansi_jemaat_a(test_db, jemaat_a):
    """Seed kuitansi di jemaat_a untuk current sabat (sabat ini / ytd)."""
    db = test_db()
    today_sabat = get_sabat_info()["tanggal_sabat"]
    k = Kuitansi(
        tenant_id=jemaat_a.id,
        id_rekap_mingguan="REKAP-A-001",
        nomor_kuitansi=f"A-{jemaat_a.id}-001",
        tanggal_sabat=today_sabat,
        nama_umat_encrypted=None,
        perpuluhan_x_angka=100_000,
        pt_angka=50_000,
        khusus_angka=0,
        total_pemberian_angka=150_000,
        total_pemberian_huruf="seratus lima puluh ribu",
        porsi_kantor_misi=100_000,
        porsi_kas_jemaat=50_000,
        porsi_khusus_misi=0,
        porsi_khusus_jemaat=0,
        status="finalized",
        created_by_user_id=1,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    db.close()
    return k


@pytest.fixture(scope="function")
def kuitansi_jemaat_b(test_db, jemaat_b):
    """Seed kuitansi di jemaat_b — HARUS tidak bocor ke BENDAHARA jemaat_a."""
    db = test_db()
    today_sabat = get_sabat_info()["tanggal_sabat"]
    k = Kuitansi(
        tenant_id=jemaat_b.id,
        id_rekap_mingguan="REKAP-B-001",
        nomor_kuitansi=f"B-{jemaat_b.id}-999",  # marker uniq untuk leak detection
        tanggal_sabat=today_sabat,
        nama_umat_encrypted=None,
        perpuluhan_x_angka=999_999,  # nominal uniq untuk leak detection
        pt_angka=888_888,
        khusus_angka=0,
        total_pemberian_angka=1_888_887,
        total_pemberian_huruf="satu juta delapan ratus delapan puluh delapan ribu",
        porsi_kantor_misi=999_999,
        porsi_kas_jemaat=888_888,
        porsi_khusus_misi=0,
        porsi_khusus_jemaat=0,
        status="finalized",
        created_by_user_id=1,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    db.close()
    return k


@pytest.fixture(scope="function")
def kuitansi_jemaat_c(test_db, jemaat_c):
    """Seed kuitansi di jemaat_c (misi_lain) — uji AUDITOR_MISI cross-misi."""
    db = test_db()
    today_sabat = get_sabat_info()["tanggal_sabat"]
    k = Kuitansi(
        tenant_id=jemaat_c.id,
        id_rekap_mingguan="REKAP-C-001",
        nomor_kuitansi=f"C-{jemaat_c.id}-LEAK",
        tanggal_sabat=today_sabat,
        nama_umat_encrypted=None,
        perpuluhan_x_angka=500_000,
        pt_angka=0,
        khusus_angka=0,
        total_pemberian_angka=500_000,
        total_pemberian_huruf="lima ratus ribu",
        porsi_kantor_misi=500_000,
        porsi_kas_jemaat=0,
        porsi_khusus_misi=0,
        porsi_khusus_jemaat=0,
        status="finalized",
        created_by_user_id=1,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    db.close()
    return k


def _login(client, username, password):
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ===== Tests =====

class TestSabatIniCrossTenantLeakage:
    """GET /agregat/sabat-ini — verify BENDAHARA_A tidak lihat data jemaat_b."""

    def test_bendahara_a_does_not_see_jemaat_b_kuitansi(
        self, client, bendahara_a, kuitansi_jemaat_a, kuitansi_jemaat_b
    ):
        """BENDAHARA jemaat_a query sabat-ini: HANYA data jemaat_a muncul."""
        token = _login(client, "bendahara", "Bendahara123!")
        resp = client.get("/api/v1/agregat/sabat-ini", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("items", [])

        # LEAK DETECTION: pastikan data jemaat_b TIDAK bocor
        leaked_nomor = [i for i in items if i.get("nomor_kuitansi", "").startswith("B-")]
        assert leaked_nomor == [], (
            f"LEAK: BENDAHARA_A lihat kuitansi jemaat_b: {leaked_nomor}"
        )
        # LEAK DETECTION: nominal unik jemaat_b tidak boleh muncul
        all_nominal = sum(i.get("perpuluhan_x_angka", 0) for i in items)
        # jemaat_a punya 100_000, jemaat_b punya 999_999. Harus == 100_000
        assert all_nominal == 100_000, (
            f"LEAK: total perpuluhan_x_angka = {all_nominal} (expected 100_000, "
            f"999_999 dari jemaat_b bocor)"
        )


class TestYtdCrossTenantLeakage:
    """GET /agregat/ytd — verify BENDAHARA_A tidak lihat data jemaat_b."""

    def test_bendahara_a_does_not_see_jemaat_b_kuitansi_in_ytd(
        self, client, bendahara_a, kuitansi_jemaat_a, kuitansi_jemaat_b
    ):
        token = _login(client, "bendahara", "Bendahara123!")
        resp = client.get("/api/v1/agregat/ytd", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # YTD mengembalikan grand_total_x. jemaat_a = 100_000, jemaat_b = 999_999.
        # Kalau bocor, total != 100_000
        total_x = body.get("total_perpuluhan", 0)
        assert total_x == 100_000, (
            f"LEAK YTD: total_perpuluhan={total_x} (expected 100_000, "
            f"data jemaat_b kemungkinan bocor)"
        )


class TestKuitansiSearchCrossTenantLeakage:
    """GET /kuitansi/search — verify BENDAHARA_A tidak lihat data jemaat_b."""

    def test_bendahara_a_search_excludes_jemaat_b(
        self, client, bendahara_a, kuitansi_jemaat_a, kuitansi_jemaat_b
    ):
        token = _login(client, "bendahara", "Bendahara123!")
        resp = client.get("/api/v1/kuitansi/search?per_page=500", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        items = body.get("items", [])
        leaked = [i for i in items if str(i.get("nomor_kuitansi", "")).startswith("B-")]
        assert leaked == [], f"LEAK search: BENDAHARA_A lihat jemaat_b items: {leaked}"

        # Verify tenant_id filter — semua items HARUS tenant_a
        tenant_ids = {i.get("tenant_id") for i in items}
        assert len(tenant_ids) == 1, (
            f"LEAK search: tenant_ids multi={tenant_ids} (expected only jemaat_a)"
        )


class TestSyncUploadCrossTenantLeakage:
    """POST /sync/upload — BENDAHARA_A only upload jemaat_a (BUKAN jemaat_b)."""

    def test_bendahara_a_upload_only_sees_jemaat_a(
        self, client, bendahara_a, kuitansi_jemaat_a, kuitansi_jemaat_b, test_db
    ):
        """Upload dari BENDAHARA_A: query filter tenant_id == jemaat_a.id.
        Seharusnya uploaded count = 1 (kuitansi_jemaat_a), BUKAN 2."""
        token = _login(client, "bendahara", "Bendahara123!")
        resp = client.post("/api/v1/sync/upload", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body.get("uploaded") == 1, (
            f"LEAK upload: BENDAHARA_A uploaded={body.get('uploaded')} (expected 1). "
            f"Kalau 2, kuitansi jemaat_b ikut ter-upload."
        )
        assert body.get("tenant_id") != kuitansi_jemaat_b.tenant_id


class TestSyncPullCrossTenantLeakage:
    """GET /sync/pull — FASE4-S6H security fix verification (cross-tenant)."""

    def test_auditor_misi_only_pulls_own_misi_outboxes(
        self, client, auditor_misi, bendahara_a, kuitansi_jemaat_a, kuitansi_jemaat_b,
        kuitansi_jemaat_c, test_db
    ):
        """AUDITOR_MISI jemaat_a (misi_minahasa) harusnya PULL outbox jemaat_a+b,
        TIDAK jemaat_c (misi_lain).

        Step:
        1. Trigger upload 3× via sync/upload (BENDAHARA_A, BENDAHARA_B, BENDAHARA_C)
        2. Auditor pull → assert count == 2 (only misi_minahasa), TIDAK == 3
        """
        # Seed BENDAHARA_B and BENDAHARA_C. Kuitansi tidak punya relasi
        # `.tenant` (cuma FK integer) — lookup Tenant via tenant_id.
        db = test_db()
        tenant_b = db.query(Tenant).filter(Tenant.id == kuitansi_jemaat_b.tenant_id).first()
        tenant_c = db.query(Tenant).filter(Tenant.id == kuitansi_jemaat_c.tenant_id).first()
        for tenant_obj, uname in [(tenant_b, "bendahara_b"),
                                   (tenant_c, "bendahara_c")]:
            u = User(
                username=uname,
                nama_lengkap=f"Bendahara {tenant_obj.initial_jemaat}",
                password_hash=hash_password("Bendahara123!"),
                role="BENDAHARA",
                tenant_id=tenant_obj.id,
                is_active=True,
            )
            db.add(u)
        db.commit()
        db.close()

        # Login as each bendahara, upload
        for uname in ["bendahara", "bendahara_b", "bendahara_c"]:
            tok = _login(client, uname, "Bendahara123!")
            r = client.post("/api/v1/sync/upload", headers=_h(tok))
            assert r.status_code == 200, f"upload {uname}: {r.text}"

        # AUDITOR_MISI pull
        tok = _login(client, "auditor_misi", "AuditMisi123!")
        resp = client.get("/api/v1/sync/pull", headers=_h(tok))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("items", [])

        # S6H fix: auditor sees jemaat_a + jemaat_b (same misi) = 2, NOT 3
        assert len(items) == 2, (
            f"LEAK pull: auditor_misi see {len(items)} items (expected 2). "
            f"Jika 3, jemaat_c bocor dari misi_lain."
        )
        # LEAK DETECTION: tenant_id jemaat_c TIDAK boleh muncul
        leaked_c = [i for i in items if i.get("tenant_id") == kuitansi_jemaat_c.tenant_id]
        assert leaked_c == [], (
            f"LEAK pull: auditor_misi lihat jemaat_c (misi_lain): {leaked_c}"
        )


class TestCrossMisiAuditIsolation:
    """AUDITOR_MISI jemaat_a HARUS tidak lihat jemaat_c di misi_lain
    walaupun uni sama (uni_dk)."""

    def test_auditor_misi_agregat_excludes_other_misi(
        self, client, auditor_misi, kuitansi_jemaat_a, kuitansi_jemaat_b,
        kuitansi_jemaat_c
    ):
        """Hit agregat/sabat-ini sebagai AUDITOR_MISI → assert ZERO jemaat_c leakage.

        Skenario 'audit' (bukan 'tenant'): response berisi summary per jemaat
        (no per-kuitansi rows). Cross-misi jemaat_c tidak boleh muncul.
        """
        token = _login(client, "auditor_misi", "AuditMisi123!")
        resp = client.get("/api/v1/agregat/sabat-ini", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("items", [])

        # Auditor mode: items adalah list jemaat-summary. Cek tidak ada jemaat_c.
        # Look for nomor_kuitansi C- marker (or tenant_id indirect leak via summary).
        jemaat_c_marker = "C-"
        leaked = []
        for item in items:
            # auditor items punya key 'nomor_jemaat_summary' atau 'items' nested;
            # check all string fields untuk marker
            for v in item.values() if isinstance(item, dict) else []:
                if isinstance(v, str) and jemaat_c_marker in v:
                    leaked.append(item)
        assert leaked == [], (
            f"LEAK: AUDITOR_MISI lihat jemaat_c in sabat-ini: {leaked}"
        )

    def test_auditor_misi_search_excludes_other_misi(
        self, client, auditor_misi, kuitansi_jemaat_a, kuitansi_jemaat_b,
        kuitansi_jemaat_c
    ):
        token = _login(client, "auditor_misi", "AuditMisi123!")
        resp = client.get("/api/v1/kuitansi/search?per_page=500", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("items", [])

        # Expected: 2 items (jemaat_a, jemaat_b). TIDAK boleh 3.
        assert len(items) == 2, (
            f"LEAK search: auditor_misi see {len(items)} (expected 2). "
            f"Jika 3, jemaat_c bocor."
        )
        # Verify none have tenant_id jemaat_c
        c_tenant_id = kuitansi_jemaat_c.tenant_id
        leaked_c = [i for i in items if i.get("tenant_id") == c_tenant_id]
        assert leaked_c == [], f"LEAK search: {leaked_c}"


class TestCrossUniAdminIsolation:
    """ADMIN_UNI uni_dk HARUS tidak lihat jemaat_d di uni_lain."""

    def test_admin_uni_search_excludes_other_uni(
        self, client, admin_uni, kuitansi_jemaat_a, jemaat_d, test_db
    ):
        """Seed kuitansi di jemaat_d (uni_lain) → ADMIN_UNI uni_dk
        TIDAK boleh lihat di search."""
        # Seed kuitansi jemaat_d
        db = test_db()
        today_sabat = get_sabat_info()["tanggal_sabat"]
        k_d = Kuitansi(
            tenant_id=jemaat_d.id,
            id_rekap_mingguan="REKAP-D-001",
            nomor_kuitansi=f"D-{jemaat_d.id}-LEAK",
            tanggal_sabat=today_sabat,
            nama_umat_encrypted=None,
            perpuluhan_x_angka=1_000_000,
            pt_angka=0,
            khusus_angka=0,
            total_pemberian_angka=1_000_000,
            total_pemberian_huruf="satu juta",
            porsi_kantor_misi=1_000_000,
            porsi_kas_jemaat=0,
            porsi_khusus_misi=0,
            porsi_khusus_jemaat=0,
            status="finalized",
            created_by_user_id=1,
        )
        db.add(k_d)
        db.commit()
        db.close()

        token = _login(client, "admin_uni", "AdminUni123!")
        resp = client.get("/api/v1/kuitansi/search?per_page=500", headers=_h(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body.get("items", [])

        # Expected: 1 item (jemaat_a). TIDAK boleh 2 (yg ke-2 = jemaat_d).
        leaked_d = [i for i in items if i.get("tenant_id") == jemaat_d.id]
        assert leaked_d == [], (
            f"LEAK cross-uni: ADMIN_UNI uni_dk lihat jemaat_d uni_lain: {leaked_d}"
        )


class TestNegativeControlSanity:
    """Sanity check: jemaat_b fixture MEMANG punya data (artinya test valid)."""

    def test_jemaat_b_actually_has_data(
        self, kuitansi_jemaat_a, kuitansi_jemaat_b, kuitansi_jemaat_c
    ):
        """Kalau ini FAIL, berarti fixture kuitansi_jemaat_b tidak ke-seed."""
        assert kuitansi_jemaat_b.tenant_id != kuitansi_jemaat_a.tenant_id
        assert kuitansi_jemaat_b.perpuluhan_x_angka == 999_999
        assert kuitansi_jemaat_c.tenant_id != kuitansi_jemaat_a.tenant_id
