"""
FLIPUS v1.1 — Self-service registration endpoints (PUBLIC, no auth).

POST /api/v1/register/pendeta    — daftar Pendeta + Jemaat
POST /api/v1/register/auditor    — daftar Auditor Misi/Konferens
POST /api/v1/register/admin      — daftar Admin Uni

Setelah submit, user otomatis dibuat dengan random password.
Password ditampilkan SEKALI di response, dan dikirim via Fonnte
ke nomor WA yang diisi saat submit.

FASE 4 Sprint 6-F note:
Endpoint-endpoint di file ini SENGAJA public (tanpa `Depends(get_current_user)` /
`Depends(require_tenant_scope)`) — design-nya adalah pre-auth self-service
registration. Query `Tenant.nama_uni == uni.nama_resmi` di /admin (L384) adalah
**legitimate data lookup** (mencari parent tenant untuk Uni tsb), BUKAN
tenant-isolation filter. Audit FASE4-S6 meng-flag ini, tapi setelah review
diklasifikasikan sebagai **false positive** — tidak perlu dimigrasi ke
`require_tenant_scope` karena akan BREAK alur public registration.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.master import Uni, MisiKonferens
from app.services.user_creator import (
    register_pendeta,
    register_auditor,
    register_admin,
)
from app.services.whatsapp import send_simple_message
from app.services.notification_service import create_notification, EventType
from app.models.user import User
from app.utils.password_gen import mask_password

router = APIRouter()


# ===== INPUT SCHEMAS =====

class RegisterPendetaIn(BaseModel):
    uni_id: int
    misi_konferens_id: int
    nama_jemaat: str = Field(min_length=2, max_length=120)
    initial_jemaat: str = Field(min_length=2, max_length=4, description="2-4 huruf inisial jemaat, misal 'NT' untuk Nataan")
    nama_pendeta: str = Field(min_length=2, max_length=120)
    wa_pendeta: Optional[str] = Field(None, max_length=32)
    nama_ketua: str = Field(min_length=2, max_length=120)
    wa_ketua: Optional[str] = Field(None, max_length=32)
    nama_bendahara: Optional[str] = Field(None, max_length=120)
    wa_bendahara: Optional[str] = Field(None, max_length=32)


class RegisterAuditorIn(BaseModel):
    uni_id: int
    misi_konferens_id: int
    nama_bendahara_misi: str = Field(min_length=2, max_length=120)
    wa_bendahara_misi: Optional[str] = Field(None, max_length=32)
    nama_auditor: str = Field(min_length=2, max_length=120)
    wa_auditor: Optional[str] = Field(None, max_length=32)
    # Persentase Jemaat→Misi
    pct_x_jemaat: float = Field(default=1.0, ge=0.0, le=1.0)
    pct_pt_jemaat: float = Field(default=0.5, ge=0.0, le=1.0)
    pct_khusus_jemaat: float = Field(default=0.0, ge=0.0, le=1.0)


class RegisterAdminIn(BaseModel):
    uni_id: int
    nama_bendahara_uni: str = Field(min_length=2, max_length=120)
    wa_bendahara_uni: Optional[str] = Field(None, max_length=32)
    nama_admin_uni: str = Field(min_length=2, max_length=120)
    wa_admin_uni: Optional[str] = Field(None, max_length=32)
    # Persentase Misi→Uni
    pct_x_uni: float = Field(default=0.0, ge=0.0, le=1.0)
    pct_pt_uni: float = Field(default=0.0, ge=0.0, le=1.0)
    pct_khusus_uni: float = Field(default=0.0, ge=0.0, le=1.0)


# ===== OUTPUT SCHEMAS =====

class CredentialsOut(BaseModel):
    """Kredensial user baru. Ditampilkan SEKALI di response."""
    username: str
    password: str  # plain — hanya muncul sekali
    password_masked: str
    nomor_wa_target: Optional[str]
    wa_sent: bool


class RegisterPendetaOut(BaseModel):
    status: str
    role: str = "PENDETA"
    user_id: int
    tenant_id: int
    nama_jemaat: str
    nama_pendeta: str
    credentials: CredentialsOut
    message: str


class RegisterAuditorOut(BaseModel):
    status: str
    role: str = "AUDITOR_MISI"
    user_id: int
    tenant_id: int
    misi_id: int
    nama_misi: str
    nama_auditor: str
    credentials: CredentialsOut
    message: str


class RegisterAdminOut(BaseModel):
    status: str
    role: str = "ADMIN_UNI"
    user_id: int
    tenant_id: int
    uni_id: int
    nama_uni: str
    nama_admin: str
    credentials: CredentialsOut
    message: str


# ===== HELPERS =====

def _send_credentials_wa(phone: Optional[str], username: str, password: str, role_label: str, unit_name: str) -> bool:
    """Kirim kredensial via Fonnte. Return True kalau sent (atau mock-skipped karena WHATSAPP_ENABLED=false)."""
    if not phone:
        return False
    msg = (
        f"*SELAMAT DATANG DI FLIPUS*\n\n"
        f"Shalom,\n\n"
        f"Akun {role_label} untuk {unit_name} telah aktif di FLIPUS.\n\n"
        f"*Kredensial Anda:*\n"
        f"Username: {username}\n"
        f"Password: {password}\n\n"
        f"Login di: [link app akan dikirim setelah deploy]\n\n"
        f"Segera ganti password setelah login pertama.\n\n"
        f"— Sistem FLIPUS (auto-register)"
    )
    resp = send_simple_message(phone, msg)
    if isinstance(resp, dict):
        # 'status' = 'sent' kalau WA aktif, atau 'error'/'skipped' kalau tidak
        return resp.get("status") == "sent"
    return False


def _resolve_uni_misi(db: Session, uni_id: int, misi_id: int) -> tuple[Uni, MisiKonferens]:
    uni = db.query(Uni).filter(Uni.id == uni_id).first()
    if not uni:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Uni id {uni_id} tidak ditemukan")
    misi = db.query(MisiKonferens).filter(MisiKonferens.id == misi_id).first()
    if not misi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Misi id {misi_id} tidak ditemukan")
    if misi.uni_id != uni.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Misi {misi.kode} bukan bagian dari Uni {uni.kode}")
    return uni, misi


# ===== ENDPOINTS =====

@router.post("/pendeta", tags=['Register'], response_model=RegisterPendetaOut)
def register_pendeta_endpoint(payload: RegisterPendetaIn, db: Session = Depends(get_db)):
    """
    Self-service registrasi Pendeta.

    Flow:
    1. Validasi Uni & Misi exists dan terikat
    2. Create/get Tenant (Jemaat)
    3. Create User Pendeta dengan password random
    4. Kirim kredensial via WA ke nomor Pendeta (jika diisi)
    5. Return kredensial di response (untuk ditunjukkan ke user di success page)
    """
    uni, misi = _resolve_uni_misi(db, payload.uni_id, payload.misi_konferens_id)

    try:
        user, plain_password, tenant = register_pendeta(
            db=db,
            uni=uni,
            misi=misi,
            nama_jemaat=payload.nama_jemaat,
            initial_jemaat=payload.initial_jemaat,
            nama_pendeta=payload.nama_pendeta,
            wa_pendeta=payload.wa_pendeta,
            nama_ketua=payload.nama_ketua,
            wa_ketua=payload.wa_ketua,
            nama_bendahara=payload.nama_bendahara or "",
            wa_bendahara=payload.wa_bendahara,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Gagal membuat akun: {e}")

    wa_sent = _send_credentials_wa(
        payload.wa_pendeta, user.username, plain_password,
        "Pendeta", payload.nama_jemaat,
    )

    # T24: Notify all admins about new Pendeta registration
    all_admins = (
        db.query(User)
        .filter(User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
        .all()
    )
    for admin in all_admins:
        create_notification(
            db,
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            event_type=EventType.PENDETA_REGISTERED,
            title="Pendeta baru terdaftar",
            message=(
                f"Pendeta {payload.nama_pendeta} mendaftarkan jemaat "
                f"{payload.nama_jemaat} ({misi.nama_resmi})."
            ),
            link="/admin",
            related_entity_type="user",
            related_entity_id=str(user.id),
            extra_data={
                "nama_jemaat": payload.nama_jemaat,
                "nama_pendeta": payload.nama_pendeta,
                "misi": misi.nama_resmi,
                "uni": uni.nama_resmi,
            },
            commit=False,
        )
    db.commit()

    return RegisterPendetaOut(
        status="ok",
        user_id=user.id,
        tenant_id=tenant.id,
        nama_jemaat=tenant.nama_jemaat_lokal,
        nama_pendeta=user.nama_lengkap,
        credentials=CredentialsOut(
            username=user.username,
            password=plain_password,
            password_masked=mask_password(plain_password),
            nomor_wa_target=payload.wa_pendeta,
            wa_sent=wa_sent,
        ),
        message="Akun Pendeta berhasil dibuat. Kredensial ditampilkan di bawah — simpan dengan aman.",
    )


@router.post("/auditor", tags=['Register'], response_model=RegisterAuditorOut)
def register_auditor_endpoint(payload: RegisterAuditorIn, db: Session = Depends(get_db)):
    """
    Self-service registrasi Auditor Misi/Konferens.

    Flow mirip Pendeta, plus create/update PersentaseConfig (MISI).
    """
    uni, misi = _resolve_uni_misi(db, payload.uni_id, payload.misi_konferens_id)

    try:
        user, plain_password, _ = register_auditor(
            db=db,
            uni=uni,
            misi=misi,
            nama_bendahara_misi=payload.nama_bendahara_misi,
            wa_bendahara_misi=payload.wa_bendahara_misi,
            nama_auditor=payload.nama_auditor,
            wa_auditor=payload.wa_auditor,
            pct_x_jemaat=payload.pct_x_jemaat,
            pct_pt_jemaat=payload.pct_pt_jemaat,
            pct_khusus_jemaat=payload.pct_khusus_jemaat,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Gagal membuat akun: {e}")

    wa_sent = _send_credentials_wa(
        payload.wa_auditor, user.username, plain_password,
        "Auditor", misi.nama_resmi,
    )

    # T24: Notify all admins about new Auditor registration
    all_admins = (
        db.query(User)
        .filter(User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
        .all()
    )
    for admin in all_admins:
        create_notification(
            db,
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            event_type=EventType.AUDITOR_REGISTERED,
            title="Auditor Misi baru terdaftar",
            message=(
                f"Auditor {payload.nama_auditor} terdaftar untuk misi {misi.nama_resmi} "
                f"di uni {uni.nama_resmi}."
            ),
            link="/admin",
            related_entity_type="user",
            related_entity_id=str(user.id),
            extra_data={
                "nama_auditor": payload.nama_auditor,
                "misi": misi.nama_resmi,
                "uni": uni.nama_resmi,
            },
            commit=False,
        )
    db.commit()

    # Ambil tenant_id (placeholder yang dibuat user_creator)
    from app.models.tenant import Tenant
    tenant = db.query(Tenant).filter(Tenant.misi_konferens_id == misi.id).first()

    return RegisterAuditorOut(
        status="ok",
        user_id=user.id,
        tenant_id=tenant.id if tenant else 0,
        misi_id=misi.id,
        nama_misi=misi.nama_resmi,
        nama_auditor=user.nama_lengkap,
        credentials=CredentialsOut(
            username=user.username,
            password=plain_password,
            password_masked=mask_password(plain_password),
            nomor_wa_target=payload.wa_auditor,
            wa_sent=wa_sent,
        ),
        message="Akun Auditor berhasil dibuat. Konfigurasi persentase telah disimpan.",
    )


@router.post("/admin", tags=['Register'], response_model=RegisterAdminOut)
def register_admin_endpoint(payload: RegisterAdminIn, db: Session = Depends(get_db)):
    """
    Self-service registrasi Admin Uni.

    Flow mirip Auditor, tapi scope persentase = UNI.
    """
    uni = db.query(Uni).filter(Uni.id == payload.uni_id).first()
    if not uni:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Uni id {payload.uni_id} tidak ditemukan")

    try:
        user, plain_password = register_admin(
            db=db,
            uni=uni,
            nama_bendahara_uni=payload.nama_bendahara_uni,
            wa_bendahara_uni=payload.wa_bendahara_uni,
            nama_admin_uni=payload.nama_admin_uni,
            wa_admin_uni=payload.wa_admin_uni,
            pct_x_uni=payload.pct_x_uni,
            pct_pt_uni=payload.pct_pt_uni,
            pct_khusus_uni=payload.pct_khusus_uni,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Gagal membuat akun: {e}")

    wa_sent = _send_credentials_wa(
        payload.wa_admin_uni, user.username, plain_password,
        "Admin Uni", uni.nama_resmi,
    )

    # T24: Notify ALL existing admins about new admin registration
    all_admins = (
        db.query(User)
        .filter(User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
        .all()
    )
    for admin in all_admins:
        create_notification(
            db,
            user_id=admin.id,
            tenant_id=admin.tenant_id,
            event_type=EventType.ADMIN_REGISTERED,
            title="Admin Uni baru terdaftar",
            message=(
                f"Admin Uni baru: {payload.nama_admin_uni} untuk uni {uni.nama_resmi}."
            ),
            link="/admin",
            related_entity_type="user",
            related_entity_id=str(user.id),
            extra_data={
                "nama_admin_uni": payload.nama_admin_uni,
                "uni": uni.nama_resmi,
            },
            commit=False,
        )
    db.commit()

    from app.models.tenant import Tenant
    tenant = db.query(Tenant).filter(
        Tenant.nama_uni == uni.nama_resmi,
        Tenant.misi_konferens_id == None,
    ).first()

    return RegisterAdminOut(
        status="ok",
        user_id=user.id,
        tenant_id=tenant.id if tenant else 0,
        uni_id=uni.id,
        nama_uni=uni.nama_resmi,
        nama_admin=user.nama_lengkap,
        credentials=CredentialsOut(
            username=user.username,
            password=plain_password,
            password_masked=mask_password(plain_password),
            nomor_wa_target=payload.wa_admin_uni,
            wa_sent=wa_sent,
        ),
        message="Akun Admin Uni berhasil dibuat. Konfigurasi persentase telah disimpan.",
    )
