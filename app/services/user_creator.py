"""
FLIPUS v1.1 — User creator service.

Helper atomic untuk self-service registration (Pendeta / Auditor / Admin Uni).
Sekaligus handle create Tenant + Uni + MisiKonferens + User + AuditLog.

Return dict berisi user_id, username, password (plain, untuk ditampilkan sekali
di response register endpoint dan dikirim via Fonnte).
"""


from sqlalchemy.orm import Session

from app.core.security import generate_tenant_signature, hash_password
from app.models.audit import AuditLog
from app.models.master import MisiKonferens, PersentaseConfig, Uni
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tenant_service import generate_unique_slug
from app.utils.password_gen import generate_random_password


# Username generator conventions
def _username_for_pendeta(initial_jemaat: str) -> str:
    """pendeta_{initial_jemaat lowercase}, max 80 chars."""
    init = initial_jemaat.lower().strip()[:8] or "jt"
    return f"pendeta_{init}"


def _username_for_auditor(kode_misi: str) -> str:
    """auditor_{kode_misi lowercase}, max 80 chars."""
    kode = kode_misi.lower().strip()[:16] or "misi"
    return f"auditor_{kode}"


def _username_for_admin(kode_uni: str) -> str:
    """admin_{kode_uni lowercase}, max 80 chars."""
    kode = kode_uni.lower().strip()[:8] or "uni"
    return f"admin_{kode}"


def _get_or_create_tenant(
    db: Session,
    uni: Uni,
    misi: MisiKonferens,
    nama_jemaat: str,
    initial_jemaat: str,
    nama_pendeta: str,
    nama_ketua: str,
    nama_bendahara: str = "",
) -> Tenant:
    """Lookup Tenant by nama_jemaat_lokal + misi_konferens_id, atau create baru."""
    tenant = (
        db.query(Tenant)
        .filter(Tenant.nama_jemaat_lokal == nama_jemaat)
        .filter(Tenant.misi_konferens_id == misi.id)
        .first()
    )
    if tenant:
        # Update field pejabat (kalau ada perubahan struktural)
        if nama_pendeta:
            tenant.nama_pendeta = nama_pendeta
        if nama_ketua:
            tenant.nama_ketua_keuangan = nama_ketua
        if nama_bendahara:
            tenant.nama_bendahara = nama_bendahara
        if initial_jemaat and not tenant.initial_jemaat:
            tenant.initial_jemaat = initial_jemaat.upper()[:4]
        # Refresh signature kalau update
        new_sig = generate_tenant_signature(
            tenant.nama_uni, tenant.nama_kantor_misi, tenant.nama_jemaat_lokal
        )
        tenant.tenant_signature = new_sig
        return tenant

    # Create new
    tenant = Tenant(
        nama_uni=uni.nama_resmi,
        nama_kantor_misi=misi.nama_resmi,
        nama_jemaat_lokal=nama_jemaat,
        initial_jemaat=initial_jemaat.upper()[:4] if initial_jemaat else None,
        nama_pendeta=nama_pendeta,
        nama_ketua_keuangan=nama_ketua,
        nama_bendahara=nama_bendahara,
        misi_konferens_id=misi.id,
    )
    tenant.tenant_signature = generate_tenant_signature(
        uni.nama_resmi, misi.nama_resmi, nama_jemaat
    )
    # Auto-generate slug (Tahap 20)
    tenant.slug = generate_unique_slug(db, nama_jemaat)
    db.add(tenant)
    db.flush()  # populate tenant.id
    return tenant


def _get_or_create_persentase_misi(
    db: Session, misi: MisiKonferens,
    pct_x: float, pct_pt: float, pct_khusus: float = 0.5,
) -> PersentaseConfig:
    """Get or create PersentaseConfig scope=MISI untuk misi ini."""
    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == "MISI")
        .filter(PersentaseConfig.ref_id == misi.id)
        .first()
    )
    if cfg:
        # Update kalau ada perubahan
        cfg.pct_x_jemaat = pct_x
        cfg.pct_pt_jemaat = pct_pt
        cfg.pct_khusus_jemaat = pct_khusus
        return cfg
    cfg = PersentaseConfig(
        scope="MISI", ref_id=misi.id,
        pct_x_jemaat=pct_x, pct_pt_jemaat=pct_pt, pct_khusus_jemaat=pct_khusus,
    )
    db.add(cfg)
    db.flush()
    return cfg


def _get_or_create_persentase_uni(
    db: Session, uni: Uni,
    pct_x: float, pct_pt: float, pct_khusus: float = 0.0,
) -> PersentaseConfig:
    """Get or create PersentaseConfig scope=UNI untuk uni ini."""
    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == "UNI")
        .filter(PersentaseConfig.ref_id == uni.id)
        .first()
    )
    if cfg:
        cfg.pct_x_uni = pct_x
        cfg.pct_pt_uni = pct_pt
        cfg.pct_khusus_uni = pct_khusus
        return cfg
    cfg = PersentaseConfig(
        scope="UNI", ref_id=uni.id,
        pct_x_uni=pct_x, pct_pt_uni=pct_pt, pct_khusus_uni=pct_khusus,
    )
    db.add(cfg)
    db.flush()
    return cfg


def _create_user(
    db: Session,
    tenant_id: int,
    username: str,
    nama_lengkap: str,
    nomor_whatsapp: str | None,
    role: str,
    password: str,
) -> User:
    """Create User with hashed password. Username harus unique — caller validasi dulu.

    v1.5-E: nomor_whatsapp disimpan di dua kolom:
    - nomor_whatsapp: plain (untuk lookup: login by phone, blast search)
    - nomor_whatsapp_encrypted: Fernet (untuk display di API response)
    """
    from app.core.security import encrypt_pii
    encrypted_wa = encrypt_pii(nomor_whatsapp) if nomor_whatsapp else None
    user = User(
        tenant_id=tenant_id,
        username=username,
        password_hash=hash_password(password),
        nama_lengkap=nama_lengkap,
        nomor_whatsapp=nomor_whatsapp,
        nomor_whatsapp_encrypted=encrypted_wa,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _audit_register(db: Session, tenant_id: int, user: User, role: str) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        action=f"REGISTER_SELF_SERVICE_role_{role}_user_{user.id}",
        payload_hash=user.username,
    ))
    db.flush()


# ===== PUBLIC API =====

def register_pendeta(
    db: Session,
    uni: Uni,
    misi: MisiKonferens,
    nama_jemaat: str,
    initial_jemaat: str,
    nama_pendeta: str,
    wa_pendeta: str | None,
    nama_ketua: str,
    wa_ketua: str | None,
    nama_bendahara: str = "",
    wa_bendahara: str | None = None,
) -> tuple[User, str, Tenant]:
    """
    Create Jemaat (Tenant) + User Pendeta atomic.
    Returns: (user, plain_password, tenant)
    """
    tenant = _get_or_create_tenant(
        db, uni, misi, nama_jemaat, initial_jemaat,
        nama_pendeta, nama_ketua, nama_bendahara,
    )
    username = _username_for_pendeta(initial_jemaat or nama_jemaat)
    # Handle username collision (jemaat dengan initial sama)
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        username = f"{username}_{tenant.id}"

    password = generate_random_password(length=8)
    user = _create_user(
        db, tenant.id, username, nama_pendeta, wa_pendeta,
        "PENDETA", password,
    )
    _audit_register(db, tenant.id, user, "PENDETA")
    db.commit()
    db.refresh(user)
    return user, password, tenant


def register_auditor(
    db: Session,
    uni: Uni,
    misi: MisiKonferens,
    nama_bendahara_misi: str,
    wa_bendahara_misi: str | None,
    nama_auditor: str,
    wa_auditor: str | None,
    pct_x_jemaat: float,
    pct_pt_jemaat: float,
    pct_khusus_jemaat: float = 0.0,
) -> tuple[User, str, MisiKonferens]:
    """
    Create PersentaseConfig (MISI) + User Auditor atomic.
    Returns: (user, plain_password, misi)
    """
    _get_or_create_persentase_misi(
        db, misi, pct_x_jemaat, pct_pt_jemaat, pct_khusus_jemaat,
    )
    username = _username_for_auditor(misi.kode)
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        username = f"{username}_{misi.id}"

    # Auditor perlu tenant_id — pakai tenant "default" di misi ini
    # (kalau belum ada jemaat, kita buat tenant placeholder untuk Auditor)
    tenant = db.query(Tenant).filter(Tenant.misi_konferens_id == misi.id).first()
    if not tenant:
        tenant = Tenant(
            nama_uni=uni.nama_resmi,
            nama_kantor_misi=misi.nama_resmi,
            nama_jemaat_lokal=f"[AUDITOR-{misi.kode}]",
            initial_jemaat=f"AD{misi.id}",
            nama_pendeta="",
            nama_ketua_keuangan="",
            nama_bendahara=nama_bendahara_misi,
            misi_konferens_id=misi.id,
        )
        tenant.tenant_signature = generate_tenant_signature(
            uni.nama_resmi, misi.nama_resmi, tenant.nama_jemaat_lokal
        )
        tenant.slug = generate_unique_slug(db, tenant.nama_jemaat_lokal)
        db.add(tenant)
        db.flush()

    password = generate_random_password(length=8)
    user = _create_user(
        db, tenant.id, username, nama_auditor, wa_auditor,
        "AUDITOR_MISI", password,
    )
    _audit_register(db, tenant.id, user, "AUDITOR_MISI")
    db.commit()
    db.refresh(user)
    return user, password, misi


def register_admin(
    db: Session,
    uni: Uni,
    nama_bendahara_uni: str,
    wa_bendahara_uni: str | None,
    nama_admin_uni: str,
    wa_admin_uni: str | None,
    pct_x_uni: float,
    pct_pt_uni: float,
    pct_khusus_uni: float = 0.0,
) -> tuple[User, str]:
    """
    Create PersentaseConfig (UNI) + User Admin atomic.
    Returns: (user, plain_password)
    """
    _get_or_create_persentase_uni(
        db, uni, pct_x_uni, pct_pt_uni, pct_khusus_uni,
    )
    username = _username_for_admin(uni.kode)
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        username = f"{username}_{uni.id}"

    # Admin Uni juga butuh tenant_id — sama seperti Auditor, buat placeholder
    tenant = (
        db.query(Tenant)
        .filter(Tenant.misi_konferens_id is None)
        .filter(Tenant.nama_uni == uni.nama_resmi)
        .first()
    )
    if not tenant:
        tenant = Tenant(
            nama_uni=uni.nama_resmi,
            nama_kantor_misi="[ADMIN-UNI]",
            nama_jemaat_lokal=f"[ADMIN-{uni.kode}]",
            initial_jemaat=f"AU{uni.id}",
            nama_pendeta="",
            nama_ketua_keuangan="",
            nama_bendahara=nama_bendahara_uni,
            misi_konferens_id=None,
        )
        tenant.tenant_signature = generate_tenant_signature(
            uni.nama_resmi, tenant.nama_kantor_misi, tenant.nama_jemaat_lokal
        )
        tenant.slug = generate_unique_slug(db, tenant.nama_jemaat_lokal)
        db.add(tenant)
        db.flush()

    password = generate_random_password(length=8)
    user = _create_user(
        db, tenant.id, username, nama_admin_uni, wa_admin_uni,
        "ADMIN_UNI", password,
    )
    _audit_register(db, tenant.id, user, "ADMIN_UNI")
    db.commit()
    db.refresh(user)
    return user, password
