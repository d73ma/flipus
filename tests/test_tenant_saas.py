"""
FLIPUS v1.3 — Tahap 20 Integration Tests.

Test yang divalidate:
- TestTenantSlug: slug generator menghasilkan unique slug
- TestTenantResolution: resolve by slug/subdomain/id
- TestInactiveTenantReject: login ditolak untuk tenant.status='suspended'
- TestCrossTenantBlock: login dengan tenant_slug yang salah ditolak + audit log
- TestTenantAdminEndpoints: ADMIN_UNI bisa list/update tenant di uni-nya
- TestRegisterFlow: register pendeta create tenant dengan slug
- TestAuthBackfillSlug: legacy tenant auto-backfill slug setelah login

Run dengan:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 -m pytest tests/test_tenant_saas.py -v
"""

import os

# Set test env sebelum import app
os.environ["DATABASE_URL_LOCAL"] = "sqlite:///./test_flipus_t20.db"
os.environ["SECRET_KEY"] = "test-secret-key-t20-do-not-use-in-prod"
os.environ["PII_ENCRYPTION_KEY"] = "k7XQz9pV3mR2nT8sW1yA4bC6dE5fG0hI="
os.environ["LICENSE_TENANT_SIGNATURE_SALT"] = "test-salt-t20"

from app.core.security import generate_tenant_signature, hash_password
from app.models.audit import AuditLog
from app.models.master import MisiKonferens, Uni
from app.models.tenant import Tenant
from app.models.user import User

# ===== Test DB setup removed — pakai conftest.py =====


# ===== Helpers =====

def _create_tenant(db, slug, nama_jemaat, status="active", plan="free", uni="UKIKT", misi="DK Minahasa"):
    """Create tenant dengan signature."""
    t = Tenant(
        tenant_signature=generate_tenant_signature(uni, misi, nama_jemaat),
        nama_uni=uni,
        nama_kantor_misi=misi,
        nama_jemaat_lokal=nama_jemaat,
        slug=slug,
        plan=plan,
        status=status,
        is_active=(status == "active"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _create_user(db, tenant, username, password, role="BENDAHARA", wa=None, is_active=True):
    u = User(
        tenant_id=tenant.id,
        username=username,
        password_hash=hash_password(password),
        nama_lengkap=username.title(),
        nomor_whatsapp=wa,
        role=role,
        is_active=is_active,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ===== Tests =====

class TestTenantSlug:
    def test_slugify_basic(self):
        from app.services.tenant_service import slugify
        assert slugify("Jemaat Nataan Ratahan") == "jemaat-nataan-ratahan"
        assert slugify("GMAHK Kec. Tombatu") == "gmahk-kec-tombatu"
        assert slugify("Stadion 123!") == "stadion-123"
        assert slugify("") == "tenant"
        assert slugify("...---...") == "tenant"

    def test_slugify_reserved(self):
        from app.services.tenant_service import slugify
        assert slugify("admin") == "admin-jemaat"
        assert slugify("API") == "api-jemaat"
        assert slugify("system") == "system-jemaat"

    def test_generate_unique_slug_no_collision(self, test_db):
        from app.services.tenant_service import generate_unique_slug
        db = test_db()
        _create_tenant(db, "nataan", "Jemaat Nataan")
        # Generate slug for new tenant with different name
        slug = generate_unique_slug(db, "Jemaat Tombatu")
        assert slug == "jemaat-tombatu"

    def test_generate_unique_slug_collision(self, test_db):
        from app.services.tenant_service import generate_unique_slug
        db = test_db()
        _create_tenant(db, "jemaat-tombatu", "Jemaat Tombatu")
        slug = generate_unique_slug(db, "Jemaat Tombatu")
        assert slug == "jemaat-tombatu-2"

    def test_generate_unique_slug_triple_collision(self, test_db):
        from app.services.tenant_service import generate_unique_slug
        db = test_db()
        _create_tenant(db, "jemaat-x", "Jemaat X")
        _create_tenant(db, "jemaat-x-2", "Jemaat X 2")
        slug = generate_unique_slug(db, "Jemaat X")
        assert slug == "jemaat-x-3"


class TestTenantResolution:
    def test_get_by_slug(self, test_db):
        from app.services.tenant_service import get_tenant_by_slug
        db = test_db()
        t = _create_tenant(db, "nataan", "Jemaat Nataan")
        found = get_tenant_by_slug(db, "nataan")
        assert found is not None
        assert found.id == t.id

    def test_get_by_slug_case_insensitive(self, test_db):
        from app.services.tenant_service import get_tenant_by_slug
        db = test_db()
        _create_tenant(db, "nataan", "Jemaat Nataan")
        found = get_tenant_by_slug(db, "NATAAN")
        assert found is not None

    def test_get_by_slug_or_subdomain(self, test_db):
        from app.services.tenant_service import get_tenant_by_slug_or_subdomain
        db = test_db()
        t = _create_tenant(db, "nataan", "Jemaat Nataan")
        t.subdomain = "nataan-ratahan"
        db.commit()
        # Lookup by slug
        f1 = get_tenant_by_slug_or_subdomain(db, "nataan")
        assert f1.id == t.id
        # Lookup by subdomain
        f2 = get_tenant_by_slug_or_subdomain(db, "nataan-ratahan")
        assert f2.id == t.id


class TestInactiveTenantReject:
    """PENTING: tenant.status != 'active' HARUS reject login + protected endpoints."""

    def test_login_suspended_tenant_rejected(self, client, test_db):
        db = test_db()
        t = _create_tenant(db, "suspended-jt", "Jemaat Suspended", status="suspended")
        _create_user(db, t, "bendum", "Test1234!", role="BENDAHARA")

        resp = client.post("/api/v1/auth/login", json={
            "username": "bendum",
            "password": "Test1234!",
        })
        assert resp.status_code == 403
        assert "berstatus" in resp.json()["detail"].lower()

    def test_login_archived_tenant_rejected(self, client, test_db):
        db = test_db()
        t = _create_tenant(db, "archived-jt", "Jemaat Archived", status="archived")
        _create_user(db, t, "bendum", "Test1234!", role="BENDAHARA")

        resp = client.post("/api/v1/auth/login", json={
            "username": "bendum",
            "password": "Test1234!",
        })
        assert resp.status_code == 403

    def test_protected_endpoint_rejects_suspended_tenant(self, client, test_db):
        """Setelah login (jika somehow bisa), protected endpoint reject."""
        db = test_db()
        t = _create_tenant(db, "suspended-jt", "Jemaat Suspended", status="suspended")
        u = _create_user(db, t, "bendum", "Test1234!", role="BENDAHARA")

        # Simulate user has cached token tapi tenant sekarang suspended
        # (harus reject di get_current_user)
        from app.core.security import create_access_token
        token = create_access_token({
            "sub": u.id, "role": u.role, "tenant_id": t.id,
        })

        resp = client.get("/api/v1/agregat/tenant", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "berstatus" in resp.json()["detail"].lower()


class TestCrossTenantBlock:
    """Cek: login dengan tenant_slug yang salah → 403 + audit log."""

    def test_login_with_wrong_tenant_slug_rejected(self, client, test_db):
        db = test_db()
        t_a = _create_tenant(db, "nataan", "Jemaat Nataan")
        _create_user(db, t_a, "bendum_a", "Test1234!", role="BENDAHARA")

        # User B exists di tenant B, mencoba login dengan tenant_slug tenant A
        t_b = _create_tenant(db, "tombatu", "Jemaat Tombatu")
        _create_user(db, t_b, "bendum_b", "Test1234!", role="BENDAHARA")

        resp = client.post("/api/v1/auth/login", json={
            "username": "bendum_b",
            "password": "Test1234!",
            "tenant_slug": "nataan",  # SALAH
        })
        assert resp.status_code == 403
        # Cek audit log
        db.expire_all()
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action.like("CROSS_TENANT_BLOCKED_LOGIN%"))
            .first()
        )
        assert audit is not None
        assert "user_" in audit.action

    def test_login_correct_tenant_slug_succeeds(self, client, test_db):
        db = test_db()
        t = _create_tenant(db, "nataan", "Jemaat Nataan")
        _create_user(db, t, "bendum", "Test1234!", role="BENDAHARA")

        resp = client.post("/api/v1/auth/login", json={
            "username": "bendum",
            "password": "Test1234!",
            "tenant_slug": "nataan",  # COCOK
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_slug"] == "nataan"
        assert data["tenant_status"] == "active"


class TestTenantAdminEndpoints:
    """ADMIN_UNI can list/update tenant status/plan."""

    def _setup_admin_uni(self, db):
        """Create Uni + Misi + Admin Uni user + 2 tenants.

        FASE 4 S6-F: tambah MisiKonferens chain agar TenantScope untuk ADMIN_UNI
        bisa resolve visible_tenant_ids via Uni → MisiKonferens → Tenant.
        Tanpa misi record, `visible_tenant_ids` = [] → 403.
        """
        uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)

        # Misi placeholder (chain Uni → Misi → Tenant untuk TenantScope)
        misi = MisiKonferens(
            uni_id=uni.id,
            nama_resmi="Daerah Konferens Minahasa",
            kode="DKMI",
            jenis="MISI",
        )
        db.add(misi)
        db.commit()
        db.refresh(misi)

        # Admin placeholder tenant
        admin_tenant = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "[ADMIN-UNI]", "[ADMIN-UKIKT]"),
            nama_uni="UKIKT",
            nama_kantor_misi="[ADMIN-UNI]",
            nama_jemaat_lokal="[ADMIN-UKIKT]",
            slug="admin-ukikt",
            misi_konferens_id=None,
        )
        db.add(admin_tenant)
        db.commit()
        db.refresh(admin_tenant)

        admin = User(
            tenant_id=admin_tenant.id,
            username="admin_ukikt",
            password_hash=hash_password("Adm1n1234!"),
            nama_lengkap="Admin UKIKT",
            role="ADMIN_UNI",
            is_active=True,
        )
        db.add(admin)
        db.commit()

        # 2 jemaat tenants (attach ke misi via misi_konferens_id)
        t_a = _create_tenant(db, "nataan", "Jemaat Nataan", uni="UKIKT")
        t_a.misi_konferens_id = misi.id
        db.commit()
        db.refresh(t_a)
        t_b = _create_tenant(db, "tombatu", "Jemaat Tombatu", uni="UKIKT")
        t_b.misi_konferens_id = misi.id
        db.commit()
        db.refresh(t_b)

        return admin_tenant, admin, t_a, t_b

    def test_admin_can_list_tenants_in_uni(self, client, test_db):
        db = test_db()
        admin_tenant, admin, t_a, t_b = self._setup_admin_uni(db)

        resp = client.post("/api/v1/auth/login", json={
            "username": "admin_ukikt",
            "password": "Adm1n1234!",
        })
        token = resp.json()["access_token"]

        resp = client.get("/api/v1/tenants", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 2
        slugs = [t["slug"] for t in data["tenants"]]
        assert "nataan" in slugs
        assert "tombatu" in slugs

    def test_admin_can_suspend_tenant(self, client, test_db):
        db = test_db()
        admin_tenant, admin, t_a, t_b = self._setup_admin_uni(db)

        resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
        token = resp.json()["access_token"]

        # Suspend tenant A
        resp = client.patch(
            f"/api/v1/tenants/{t_a.id}/status",
            json={"status": "suspended", "reason": "Test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "suspended"

        # Verify di DB
        db.expire_all()
        t_a_check = db.query(Tenant).filter(Tenant.id == t_a.id).first()
        assert t_a_check.status == "suspended"
        assert t_a_check.is_active is False

    def test_admin_can_change_plan(self, client, test_db):
        db = test_db()
        admin_tenant, admin, t_a, t_b = self._setup_admin_uni(db)

        resp = client.post("/api/v1/auth/login", json={"username": "admin_ukikt", "password": "Adm1n1234!"})
        token = resp.json()["access_token"]

        resp = client.patch(
            f"/api/v1/tenants/{t_a.id}/plan",
            json={"plan": "premium", "reason": "Test upgrade"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["plan"] == "premium"

    def test_non_admin_cannot_list_tenants(self, client, test_db):
        db = test_db()
        t = _create_tenant(db, "nataan", "Jemaat Nataan")
        _create_user(db, t, "bendum", "Test1234!", role="BENDAHARA")

        resp = client.post("/api/v1/auth/login", json={"username": "bendum", "password": "Test1234!"})
        token = resp.json()["access_token"]

        resp = client.get("/api/v1/tenants", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestRegisterFlow:
    """Register pendeta creates tenant dengan slug."""

    def test_register_creates_tenant_with_slug(self, client, test_db):
        # Setup Uni + Misi
        db = test_db()
        uni = Uni(nama_resmi="UKIKT", kode="UKIKT")
        db.add(uni)
        db.commit()
        db.refresh(uni)
        misi = MisiKonferens(
            uni_id=uni.id,
            nama_resmi="Daerah Konferens Minahasa",
            kode="DKMI",
            jenis="MISI",
        )
        db.add(misi)
        db.commit()
        db.refresh(misi)

        from app.models.master import Uni as UniModel
        assert db.query(UniModel).count() == 1

        # Register via public endpoint
        resp = client.post("/api/v1/register/pendeta", json={
            "uni_id": uni.id,
            "misi_konferens_id": misi.id,
            "nama_jemaat": "Jemaat Tombatu",
            "initial_jemaat": "TB",
            "nama_pendeta": "Pdt. Tombatu",
            "wa_pendeta": "081234567890",
            "nama_ketua": "Sdr. Ketua",
            "wa_ketua": "081234567891",
            "nama_bendahara": "Sdri. Bendahara",
            "wa_bendahara": "081234567892",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] > 0
        assert data["credentials"]["username"] == "pendeta_tb"

        # Verify tenant punya slug
        tenant = db.query(Tenant).filter(Tenant.id == data["tenant_id"]).first()
        assert tenant is not None
        assert tenant.slug == "jemaat-tombatu"
        assert tenant.status == "active"


class TestAuthBackfillSlug:
    """Legacy tenant tanpa slug (dari pre-Tahap 20) auto-backfill."""

    def test_legacy_tenant_gets_slug_on_login(self, client, test_db):
        db = test_db()
        # Create tenant tanpa slug (simulasi legacy)
        t = Tenant(
            tenant_signature=generate_tenant_signature("UKIKT", "DK Minahasa", "Jemaat Legacy"),
            nama_uni="UKIKT",
            nama_kantor_misi="DK Minahasa",
            nama_jemaat_lokal="Jemaat Legacy",
            slug=None,  # legacy
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        _create_user(db, t, "bendum_legacy", "Test1234!", role="BENDAHARA")

        # Login → must succeed & backfill slug
        resp = client.post("/api/v1/auth/login", json={
            "username": "bendum_legacy",
            "password": "Test1234!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_slug"] == "jemaat-legacy"

        # Verify slug persisted
        db.expire_all()
        t_check = db.query(Tenant).filter(Tenant.id == t.id).first()
        assert t_check.slug == "jemaat-legacy"


class TestPublicResolve:
    """GET /api/v1/tenants/resolve/{slug} — public info endpoint."""

    def test_resolve_returns_public_info(self, client, test_db):
        db = test_db()
        _create_tenant(db, "nataan", "Jemaat Nataan")

        resp = client.get("/api/v1/tenants/resolve/nataan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "nataan"
        assert data["nama_jemaat_lokal"] == "Jemaat Nataan"
        assert data["status"] == "active"
        # Public: tidak ada contact_email
        assert "contact_email" not in data

    def test_resolve_not_found(self, client, test_db):
        resp = client.get("/api/v1/tenants/resolve/tidak-ada")
        assert resp.status_code == 404
