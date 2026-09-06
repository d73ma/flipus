"""
FLIPUS v1.1 — User management endpoints (delete + list).

DELETE /api/v1/users/{user_id}    — soft-delete user (set is_active=False)
GET    /api/v1/users              — list user yang visible untuk caller

RBAC matrix:
- ADMIN_UNI: lihat/nonaktifkan user AUDITOR_MISI di uni-nya
- AUDITOR_MISI: lihat/nonaktifkan user PENDETA/BENDAHARA/KETUA_KEUANGAN di misi-nya
- (Pendeta/Ketua/Bendahara Jemaat tidak punya akses list user — return 403)

Soft-delete: is_active=False. User masih ada di DB untuk audit trail,
tapi tidak bisa login (cek di auth.py get_current_user).
"""


from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.security import decrypt_pii
from app.models.audit import AuditLog
from app.models.master import MisiKonferens, Uni
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter()


# ===== Schemas =====

class UserOut(BaseModel):
    id: int
    username: str
    nama_lengkap: str
    role: str
    nomor_whatsapp: str | None
    is_active: bool
    tenant_id: int
    # Info tambahan untuk info card
    nama_jemaat: str | None = None
    nama_misi: str | None = None
    nama_uni: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DeleteUserOut(BaseModel):
    status: str
    user_id: int
    username: str
    role: str
    deleted_by: str  # role caller


class UsersListOut(BaseModel):
    users: list[UserOut]
    count: int


# ===== Helpers =====

def _user_to_out(user: User, db: Session) -> UserOut:
    """Convert User → UserOut dengan info tenant/misi/uni.

    v1.5-E: nomor_whatsapp di-decrypt dari kolom encrypted (Fernet) untuk display.
    Fallback ke plain nomor_whatsapp kalau encrypted kosong (mis. row lama sebelum
    migration). Lookup internal (login, blast search) masih pakai plain.
    """
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    nama_jemaat = nama_misi = nama_uni = None
    if tenant:
        nama_jemaat = tenant.nama_jemaat_lokal
        nama_misi = tenant.nama_kantor_misi
        nama_uni = tenant.nama_uni
    # Prefer encrypted → decrypt. Fallback ke plain kalau encrypted kosong.
    wa_display = decrypt_pii(user.nomor_whatsapp_encrypted) if user.nomor_whatsapp_encrypted else (user.nomor_whatsapp or None)
    return UserOut(
        id=user.id,
        username=user.username,
        nama_lengkap=user.nama_lengkap,
        role=user.role,
        nomor_whatsapp=wa_display,
        is_active=user.is_active,
        tenant_id=user.tenant_id,
        nama_jemaat=nama_jemaat,
        nama_misi=nama_misi,
        nama_uni=nama_uni,
    )


def _get_callers_misi_or_uni(caller: dict, db: Session) -> tuple[MisiKonferens | None, Uni | None]:
    """Ambil Misi/Uni yang terkait dengan caller."""
    tenant = db.query(Tenant).filter(Tenant.id == caller["tenant_id"]).first()
    if not tenant:
        return None, None
    misi = None
    if tenant.misi_konferens_id:
        misi = db.query(MisiKonferens).filter(MisiKonferens.id == tenant.misi_konferens_id).first()
    uni = db.query(Uni).filter(Uni.nama_resmi == tenant.nama_uni).first() if tenant.nama_uni else None
    return misi, uni


# ===== GET /users =====

@router.get("", tags=['Users'], response_model=UsersListOut)
def list_users(
    role: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List user yang visible untuk caller.

    RBAC:
    - ADMIN_UNI: list semua AUDITOR_MISI di uni caller
    - AUDITOR_MISI: list PENDETA/BENDAHARA/KETUA_KEUANGAN di misi caller
    - lainnya: 403
    """
    caller_role = current_user["role"]

    q = db.query(User)

    if caller_role == "ADMIN_UNI":
        # Scope: uni caller → misi di uni tsb → tenant di misi tsb → user di tenant tsb
        _caller_misi, caller_uni = _get_callers_misi_or_uni(current_user, db)
        if not caller_uni:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin Uni belum terkait ke Uni manapun")
        # Misi dalam uni caller
        misi_ids = [
            m.id for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == caller_uni.id).all()
        ]
        # Tenant dalam misi-misi tsb
        tenant_ids = [
            t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id.in_(misi_ids)).all()
        ]
        q = q.filter(User.tenant_id.in_(tenant_ids))
        q = q.filter(User.role == "AUDITOR_MISI")
    elif caller_role == "AUDITOR_MISI":
        # Scope: misi caller → tenant di misi tsb → user di tenant tsb
        caller_misi, _ = _get_callers_misi_or_uni(current_user, db)
        if not caller_misi:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Auditor belum terkait ke Misi manapun")
        tenant_ids = [
            t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id == caller_misi.id).all()
        ]
        q = q.filter(User.tenant_id.in_(tenant_ids))
        q = q.filter(User.role.in_(["PENDETA", "KETUA_KEUANGAN", "BENDAHARA"]))
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role ini tidak boleh lihat daftar user")

    if role:
        q = q.filter(User.role == role)

    users = q.order_by(User.role, User.id).all()
    return UsersListOut(
        users=[_user_to_out(u, db) for u in users],
        count=len(users),
    )


# ===== DELETE /users/{user_id} =====

@router.delete("/{user_id}", tags=['Users'], response_model=DeleteUserOut)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Soft-delete user (set is_active=False).

    RBAC (sama seperti list_users):
    - ADMIN_UNI: hapus AUDITOR_MISI di uni caller
    - AUDITOR_MISI: hapus PENDETA/BENDAHARA/KETUA_KEUANGAN di misi caller
    - lainnya: 403

    User is_active=False → tidak bisa login (cek di auth.get_current_user).
    Data masih ada di DB untuk audit trail.
    """
    caller_role = current_user["role"]

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User tidak ditemukan")
    if target.id == current_user["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak bisa hapus akun sendiri")

    # Validasi scope RBAC
    if caller_role == "ADMIN_UNI":
        if target.role != "AUDITOR_MISI":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin Uni hanya boleh hapus Auditor")
        _caller_misi, caller_uni = _get_callers_misi_or_uni(current_user, db)
        if not caller_uni:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin Uni belum terkait Uni")
        # Cek target ada di uni caller
        target_tenant = db.query(Tenant).filter(Tenant.id == target.tenant_id).first()
        if not target_tenant:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant target tidak ditemukan")
        target_misi = db.query(MisiKonferens).filter(MisiKonferens.id == target_tenant.misi_konferens_id).first() if target_tenant.misi_konferens_id else None
        if not target_misi or target_misi.uni_id != caller_uni.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Auditor target di luar Uni Anda")

    elif caller_role == "AUDITOR_MISI":
        if target.role not in ("PENDETA", "KETUA_KEUANGAN", "BENDAHARA"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Auditor hanya boleh hapus jemaat (Pendeta/Ketua/Bendahara)")
        caller_misi, _ = _get_callers_misi_or_uni(current_user, db)
        if not caller_misi:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Auditor belum terkait Misi")
        target_tenant = db.query(Tenant).filter(Tenant.id == target.tenant_id).first()
        if not target_tenant or target_tenant.misi_konferens_id != caller_misi.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User target di luar Misi Anda")
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role ini tidak boleh hapus user")

    # Soft-delete
    target.is_active = False
    db.add(AuditLog(
        tenant_id=target.tenant_id,
        action=f"USER_DELETED_BY_{caller_role}_user_{current_user['id']}_target_{target.id}",
        payload_hash=target.username,
    ))
    db.commit()

    return DeleteUserOut(
        status="deleted",
        user_id=target.id,
        username=target.username,
        role=target.role,
        deleted_by=caller_role,
    )
