"""
FLIPUS v1.3 — Tahap 25 Master Test Configuration.

Provides shared fixtures for all T20-T24 regression tests + E2E scenarios.

Run full suite:
    cd /Users/jerrymauri/Flipus
    .venv/bin/python3 -m pytest tests/ -v

Run specific suite:
    .venv/bin/python3 -m pytest tests/test_t22_search_export.py -v
    .venv/bin/python3 -m pytest tests/test_t25_e2e.py -v
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import utcnow

# Set test env BEFORE importing app
os.environ["DATABASE_URL_LOCAL"] = "sqlite:///./test_flipus_t25.db"
os.environ["SECRET_KEY"] = "test-secret-key-t25-do-not-use-in-prod"
# PII_ENCRYPTION_KEY must be valid Fernet key (32 url-safe base64 bytes)
# Generate via: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
os.environ["PII_ENCRYPTION_KEY"] = "WW7LHfY_bmiNjXAiTZjmHI4w_wwPQH-_x9U722_FCDY="
os.environ["LICENSE_TENANT_SIGNATURE_SALT"] = "test-salt-t25"

from app.core.database import Base, get_db
from app.core.security import generate_tenant_signature, hash_password
from app.main import app
from app.models.master import MisiKonferens, PersentaseConfig, Uni
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User

# ===== DB Fixture =====

@pytest.fixture(scope="function")
def test_db():
    """In-memory SQLite per test function."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    return TestClient(app)


# ===== Domain Fixtures =====

@pytest.fixture(scope="function")
def uni_dk(test_db):
    """Create Uni GMAHK DK (UKIKT)."""
    db = test_db()
    uni = Uni(
        nama_resmi="GMAHK UKIKT",
        kode="UKIKT",
    )
    db.add(uni)
    db.commit()
    db.refresh(uni)
    db.close()
    return uni


@pytest.fixture(scope="function")
def misi_minahasa(test_db, uni_dk):
    """Create Misi Konferens Minahasa under UKIKT."""
    db = test_db()
    misi = MisiKonferens(
        nama_resmi="Misi DK Minahasa",
        kode="DK.MIN",
        uni_id=uni_dk.id,
        jenis="MISI",
    )
    db.add(misi)
    db.commit()
    db.refresh(misi)

    # PersentaseConfig (MISI scope)
    cfg = PersentaseConfig(
        scope="MISI",
        ref_id=misi.id,
        pct_x_jemaat=1.0,
        pct_pt_jemaat=0.5,
        pct_khusus_jemaat=0.0,
    )
    db.add(cfg)
    db.commit()
    db.close()
    return misi


@pytest.fixture(scope="function")
def jemaat_a(test_db, misi_minahasa, uni_dk):
    """Tenant A — jemaat utama untuk most tests."""
    db = test_db()
    nama_jemaat = "Jemaat Sentrum A"
    t = Tenant(
        tenant_signature=generate_tenant_signature(
            uni_dk.nama_resmi, misi_minahasa.nama_resmi, nama_jemaat
        ),
        nama_uni=uni_dk.nama_resmi,
        nama_kantor_misi=misi_minahasa.nama_resmi,
        nama_jemaat_lokal=nama_jemaat,
        initial_jemaat="SA",
        slug="jemaat-sentrum-a",
        status="active",
        plan="standard",
        nama_pendeta="Pdt. Test Pendeta",
        nama_ketua_keuangan="Sdr. Test Ketua",
        nama_bendahara="Sdr. Test Bendahara",
        misi_konferens_id=misi_minahasa.id,  # visible to admin_uni / auditor_misi scope
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    db.close()
    return t


@pytest.fixture(scope="function")
def jemaat_b(test_db, misi_minahasa, uni_dk):
    """Tenant B — jemaat kedua untuk cross-tenant testing."""
    db = test_db()
    nama_jemaat = "Jemaat Timur B"
    t = Tenant(
        tenant_signature=generate_tenant_signature(
            uni_dk.nama_resmi, misi_minahasa.nama_resmi, nama_jemaat
        ),
        nama_uni=uni_dk.nama_resmi,
        nama_kantor_misi=misi_minahasa.nama_resmi,
        nama_jemaat_lokal=nama_jemaat,
        initial_jemaat="TB",
        slug="jemaat-timur-b",
        status="active",
        plan="free",
        misi_konferens_id=misi_minahasa.id,  # visible to admin_uni scope
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    db.close()
    return t


# ===== User Fixtures =====

@pytest.fixture(scope="function")
def bendahara_a(test_db, jemaat_a):
    db = test_db()
    u = User(
        username="bendahara",
        nama_lengkap="Test Bendahara A",
        password_hash=hash_password("Bendahara123!"),
        role="BENDAHARA",
        tenant_id=jemaat_a.id,
        is_active=True,
        nomor_whatsapp="6281234567001",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture(scope="function")
def ketua_a(test_db, jemaat_a):
    db = test_db()
    u = User(
        username="ketua_keuang",
        nama_lengkap="Test Ketua A",
        password_hash=hash_password("Ketua123!"),
        role="KETUA_KEUANGAN",
        tenant_id=jemaat_a.id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture(scope="function")
def pendeta(test_db, jemaat_a):
    """Pendeta — global user, username='pendeta'."""
    db = test_db()
    u = User(
        username="pendata",
        nama_lengkap="Test Pendeta",
        password_hash=hash_password("Pendeta123!"),
        role="PENDETA",
        tenant_id=jemaat_a.id,
        is_active=True,
        nomor_whatsapp="6281234567002",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture(scope="function")
def admin_uni(test_db, jemaat_a, uni_dk):
    """Admin Uni — owns UKIKT."""
    # Use jemaat_a's tenant as carrier (placeholder pattern)
    db = test_db()
    u = User(
        username="admin_uni",
        nama_lengkap="Jerry (Admin Uni)",
        password_hash=hash_password("AdminUni123!"),
        role="ADMIN_UNI",
        tenant_id=jemaat_a.id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


@pytest.fixture(scope="function")
def auditor_misi(test_db, jemaat_a):
    """Auditor Misi — scope all jemaat in misi via tenant.misi_konferens_id chain.

    Auditor Misi diletakkan di jemaat_a (yang punya misi_konferens_id=misi_minahasa.id).
    TenantScope.resolve_visible_tenants akan follow: caller_tenant.misi_konferens_id
    → semua Tenant dg misi_konferens_id yg sama visible.
    """
    db = test_db()
    u = User(
        username="auditor_misi",
        nama_lengkap="Test Auditor",
        password_hash=hash_password("AuditMisi123!"),
        role="AUDITOR_MISI",
        tenant_id=jemaat_a.id,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


# ===== Auth Helpers =====

def login(client, username, password):
    """Login helper. Returns response with access_token."""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return resp


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def bendahara_token(client, bendahara_a):
    resp = login(client, "bendahara", "Bendahara123!")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="function")
def ketua_token(client, ketua_a):
    resp = login(client, "ketua_keuang", "Ketua123!")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="function")
def admin_token(client, admin_uni):
    resp = login(client, "admin_uni", "AdminUni123!")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="function")
def auditor_token(client, auditor_misi):
    resp = login(client, "auditor_misi", "AuditMisi123!")
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ===== Kuitansi Factory =====

@pytest.fixture(scope="function")
def create_kuitansi(test_db):
    """Factory for creating Kuitansi rows. Returns callable."""
    def _make(
        tenant_id: int,
        *,
        status: str = "finalized",
        tanggal_sabat: str = "2026-08-01",
        perpuluhan_x_angka: int = 100000,
        pt_angka: int = 50000,
        khusus_angka: int = 0,
        created_by_user_id: int = None,
        approved_by_user_id: int = None,
        id_rekap_mingguan: str = None,
    ):
        from app.core.security import encrypt_pii
        db = test_db()
        from app.utils.nomor_kuitansi import generate_id_rekap_mingguan
        if id_rekap_mingguan is None:
            id_rekap_mingguan = generate_id_rekap_mingguan()

        total = perpuluhan_x_angka + pt_angka + khusus_angka
        k = Kuitansi(
            tenant_id=tenant_id,
            id_rekap_mingguan=id_rekap_mingguan,
            nomor_kuitansi=f"KPT-TEST-{tenant_id}-{utcnow().timestamp()}",
            tanggal_sabat=tanggal_sabat,
            nama_umat_encrypted=encrypt_pii("Test Umat"),
            nomor_whatsapp_encrypted=encrypt_pii("628123456000"),
            perpuluhan_x_angka=perpuluhan_x_angka,
            pt_angka=pt_angka,
            khusus_angka=khusus_angka,
            total_pemberian_angka=total,
            total_pemberian_huruf="seratus lima puluh ribu rupiah",
            porsi_kantor_misi=perpuluhan_x_angka,
            porsi_kas_jemaat=pt_angka - (pt_angka // 2),
            porsi_khusus_misi=0,
            porsi_khusus_jemaat=0,
            status=status,
            created_by_user_id=created_by_user_id,
            approved_by_user_id=approved_by_user_id,
        )
        db.add(k)
        db.commit()
        db.refresh(k)
        db.close()
        return k
    return _make



# =====================================================================
# FASE 3-S2 (Sprint 1 K1 + Sprint 2 cleanup) — TEST ISOLATION
# ---------------------------------------------------------------------
# slowapi Limiter pakai storage_uri="memory://" (single-worker SQLite).
# Storage ini di-share across test functions in same Python process,
# sehingga test #11+ dapat 429 "Rate limit exceeded" karena testclient
# IP dianggap sama oleh limiter.
#
# Fixture autouse ini reset storage antara tests sehingga test suite
# jadi deterministik tanpa mengorbankan proteksi rate-limit di production.
# =====================================================================

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory rate-limit storage between tests.

    FASE 3-S1 K1: limiter = Limiter(key_func=get_remote_address,
    storage_uri='memory://'). Memory storage di-share dalam satu Python
    process, sehingga tanpa reset, request #11+ dari testclient (IP sama)
    akan kena 429. Fixture ini dipanggil SETIAP test (autouse) untuk
    reset storage setelah yield (post-test).
    """
    from app.core.rate_limiter import limiter
    yield
    # slowapi >= 0.1.9: storage adalah MovingWindowMemoryList dengan .reset()
    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
          try:
              storage.reset()
          except Exception:
              pass  # noqa: S110 — jika backend storage tidak support reset, skip
