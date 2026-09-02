"""v2.0 M8 — Managed Users (invite) + Void Transaksi.

Endpoints:
- POST /users/invite                              → invite user baru via WA (Bendahara/Admin Uni/Auditor Misi)
- POST /kuitansi/{kuitansi_id}/void               → soft-void Kuitansi (creator/Bendahara only)
- POST /pengeluaran/{pengeluaran_id}/void         → soft-void Pengeluaran (creator/Bendahara only)

RBAC invite:
- Bendahara: invite BENDAHARA/KETUA_KEUANGAN/PENDETA dalam tenant-nya
- AUDITOR_MISI: invite BENDAHARA/KETUA_KEUANGAN/PENDETA dalam misi-nya (assign ke jemaat manapun di misi tsb)
- ADMIN_UNI: invite AUDITOR_MISI dalam uni-nya (assign ke misi manapun di uni tsb)

Void rule:
- Hanya creator ATAU BENDAHARA yang sama tenant
- Hanya boleh void kalau status belum final (finalized Kuitansi / approved Pengeluaran)
- Kalau sudah final → 403 dengan pesan "butuh approval Auditor"
"""
import secrets
import string
import sys
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.security import hash_password
from app.models.user import User
from app.models.tenant import Tenant
from app.models.master import MisiKonferens, Uni
from app.models.transaction import Kuitansi
from app.models.pengeluaran import Pengeluaran
from app.models.audit import AuditLog
from app.services.whatsapp import send_simple_message

router = APIRouter()


# ===== Schemas =====

class InviteUserIn(BaseModel):
    nama_lengkap: str
    role: str  # 'BENDAHARA' | 'KETUA_KEUANGAN' | 'PENDETA' | 'AUDITOR_MISI'
    nomor_whatsapp: str
    # Opsional: kalau role=BENDAHARA/KETUA_KEUANGAN/PENDETA, assign ke jemaat tertentu (default tenant caller).
    # Kalau role=AUDITOR_MISI, assign ke misi tertentu (default misi caller).
    target_jemaat_id: Optional[int] = None
    target_misi_id: Optional[int] = None
    username_hint: Optional[str] = None  # kalau dikasih, dipakai sebagai base username


class InviteUserOut(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    status: str
    user_id: int
    username: str
    password_plain: str  # tampilkan sekali — caller WA-kan ke user
    nama_lengkap: str
    role: str
    tenant_id: int
    nomor_whatsapp: str
    wa_sent: bool
    wa_response: Optional[str] = None  # JSON-string, biar Pydantic tidak revalidate isi dict


class VoidOut(BaseModel):
    status: str
    entity_type: str
    entity_id: int
    nomor: str
    voided_by_user_id: int
    voided_at: str
    reason: Optional[str] = None


# ===== Helpers =====

def _generate_username(role: str, hint: Optional[str], db: Session, tenant_id: int) -> str:
    """Generate unique username. Format: <role>_<hint|random3>. Suffix _a/_b jika bentrok."""
    role_prefix = role.lower().replace("_keuangan", "")
    base = (hint or "").strip().lower()[:12].replace(" ", "_") or role_prefix
    base = "".join(c for c in base if c.isalnum() or c == "_") or role_prefix
    candidate = f"{role_prefix}_{base}"
    # Cek uniqueness, kalau bentrok tambah suffix
    suffix_idx = ord('a')
    while db.query(User).filter(User.username == candidate).filter(User.tenant_id == tenant_id).first():
        if suffix_idx > ord('z'):
            candidate = f"{role_prefix}_{base}_{secrets.token_hex(3)}"
            break
        candidate = f"{role_prefix}_{base}_{chr(suffix_idx)}"
        suffix_idx += 1
    return candidate


def _generate_temp_password() -> str:
    """Generate password random 12 char aman (uppercase+lowercase+digit+symbol)."""
    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(10))
        if (any(c.isupper() for c in pwd) and any(c.islower() for c in pwd)
                and any(c.isdigit() for c in pwd)):
            return pwd + "!"  # tambah symbol


def _resolve_target_tenant(
    caller: dict, db: Session, role: str,
    target_jemaat_id: Optional[int], target_misi_id: Optional[int],
) -> Tenant:
    """Resolve target Tenant untuk user baru berdasarkan role dan scope caller.

    - Untuk BENDAHARA/KETUA_KEUANGAN/PENDETA: target_jemaat_id → Tenant di jemaat tsb.
      Default: tenant caller. Caller harus punya akses (same tenant OR AUDITOR_MISI scope).
    - Untuk AUDITOR_MISI: target_misi_id → Tenant placeholder di misi tsb (pick first jemaat).
      Caller harus ADMIN_UNI di uni yang sama.
    """
    caller_role = caller["role"]

    if role in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA"):
        if caller_role == "BENDAHARA":
            # Bendahara hanya bisa invite jemaat role di tenant-nya sendiri.
            if target_jemaat_id and target_jemaat_id != caller["tenant_id"]:
                raise HTTPException(
                    403,
                    f"Bendahara hanya bisa invite ke jemaat sendiri (tenant_id={caller['tenant_id']}).",
                )
            tenant = db.query(Tenant).filter(Tenant.id == caller["tenant_id"]).first()
            if not tenant:
                raise HTTPException(404, "Tenant caller tidak ditemukan")
            return tenant
        elif caller_role == "AUDITOR_MISI":
            # Auditor bisa invite ke jemaat mana saja di misi-nya.
            caller_tenant = db.query(Tenant).filter(Tenant.id == caller["tenant_id"]).first()
            if not caller_tenant or not caller_tenant.misi_konferens_id:
                raise HTTPException(400, "Caller Auditor belum terkait misi")
            if target_jemaat_id:
                tenant = db.query(Tenant).filter(Tenant.id == target_jemaat_id).first()
                if not tenant or tenant.misi_konferens_id != caller_tenant.misi_konferens_id:
                    raise HTTPException(403, "Jemaat target di luar misi Anda")
                return tenant
            # Default: jemaat caller
            return caller_tenant
        else:
            raise HTTPException(403, "Role caller tidak boleh invite jemaat role")

    elif role == "AUDITOR_MISI":
        if caller_role != "ADMIN_UNI":
            raise HTTPException(403, "Hanya Admin Uni yang boleh invite Auditor Misi")
        # Resolve target tenant via target_misi_id → ambil jemaat pertama di misi tsb
        # Auditor disimpan di jemaat placeholder (sesuai seed_demo.py).
        if not target_misi_id:
            raise HTTPException(400, "target_misi_id wajib untuk invite AUDITOR_MISI")
        # Pick first tenant di misi tsb
        tenant = (
            db.query(Tenant)
            .filter(Tenant.misi_konferens_id == target_misi_id)
            .order_by(Tenant.id.asc())
            .first()
        )
        if not tenant:
            raise HTTPException(404, f"Tidak ada jemaat di misi_id={target_misi_id}")
        # Verify misi ada di uni caller
        caller_tenant = db.query(Tenant).filter(Tenant.id == caller["tenant_id"]).first()
        if not caller_tenant or not caller_tenant.nama_uni:
            raise HTTPException(400, "Admin Uni caller belum terkait Uni")
        caller_uni = db.query(Uni).filter(Uni.nama_resmi == caller_tenant.nama_uni).first()
        target_misi = db.query(MisiKonferens).filter(MisiKonferens.id == target_misi_id).first()
        if not caller_uni or not target_misi or target_misi.uni_id != caller_uni.id:
            raise HTTPException(403, "Misi target di luar Uni Anda")
        return tenant

    else:
        raise HTTPException(400, f"Role '{role}' tidak bisa di-invite lewat endpoint ini")


# ===== Endpoint 1: POST /users/invite =====

@router.post("/users/invite")  # response_model=InviteUserOut sengaja dihapus — biar return raw dict
def invite_user(
    payload: InviteUserIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Invite user baru. Auto-generate username + temp password + kirim via WA.

    RBAC: Bendahara/Auditor Misi (untuk jemaat role) atau Admin Uni (untuk Auditor).
    """
    role = payload.role.upper()
    if role not in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA", "AUDITOR_MISI"):
        raise HTTPException(400, f"Role '{role}' tidak valid untuk invite")

    # Resolve target tenant
    tenant = _resolve_target_tenant(
        current_user, db, role, payload.target_jemaat_id, payload.target_misi_id
    )

    # Normalize phone: 08xxx → 62xxx untuk konsistensi DB
    wa_raw = payload.nomor_whatsapp.strip().replace(" ", "").replace("-", "")
    if wa_raw.startswith("+62"):
        wa = "62" + wa_raw[3:].lstrip("0")
    elif wa_raw.startswith("62"):
        wa = wa_raw
    elif wa_raw.startswith("08"):
        wa = "62" + wa_raw[1:]
    elif wa_raw.startswith("8"):
        wa = "62" + wa_raw
    else:
        wa = wa_raw

    # Cek duplikat WA dalam tenant tsb
    existing = (
        db.query(User)
        .filter(User.tenant_id == tenant.id)
        .filter(User.nomor_whatsapp == wa)
        .filter(User.is_active == True)  # noqa: E712
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            f"Nomor WA {wa} sudah terdaftar di jemaat ini sebagai '{existing.username}' (role={existing.role}).",
        )

    # Generate username + password
    username = _generate_username(role, payload.username_hint, db, tenant.id)
    plain_password = _generate_temp_password()
    pw_hash = hash_password(plain_password)

    # Encrypt WA (v1.5-E pattern) — fallback ke None kalau encrypt_pii tidak ready
    wa_encrypted = None
    try:
        from app.core.security import encrypt_pii, fernet
        if fernet is not None:
            wa_encrypted = encrypt_pii(wa)
    except Exception as exc:  # noqa: BLE001
        print(f"[M8 invite] encrypt_pii skipped: {exc}", file=sys.stderr, flush=True)
        wa_encrypted = None

    # Create user
    new_user = User(
        tenant_id=tenant.id,
        username=username,
        password_hash=pw_hash,
        nama_lengkap=payload.nama_lengkap.strip(),
        nomor_whatsapp=wa,
        nomor_whatsapp_encrypted=wa_encrypted,
        role=role,
        is_active=True,
        password_changed_at=None,  # trigger first-login password change? deferred
    )
    db.add(new_user)

    # Audit (action max 64 char — pack dense)
    caller_id = current_user["id"]
    audit_action = f"USER_INVITE_c{caller_id}_t{tenant.id}_{role[:8]}"
    db.add(AuditLog(
        tenant_id=tenant.id,
        action=audit_action,
    ))
    try:
        db.commit()
        db.refresh(new_user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Gagal create user: {exc}")

    # Kirim WA — wrap semua, kalau gagal return success + warning supaya caller tidak bingung
    role_label = {
        "BENDAHARA": "Bendahara",
        "KETUA_KEUANGAN": "Ketua Keuangan",
        "PENDETA": "Pendeta",
        "AUDITOR_MISI": "Auditor Misi",
    }.get(role, role)

    wa_msg = (
        f"*FLIPUS — Undangan Akun Baru*\n\n"
        f"Yth. {payload.nama_lengkap},\n\n"
        f"Anda diundang sebagai *{role_label}* untuk jemaat:\n"
        f"• {tenant.nama_jemaat_lokal or '?'}\n"
        f"• Uni: {tenant.nama_uni or '?'}\n"
        f"• Misi: {tenant.nama_kantor_misi or '?'}\n\n"
        f"*Kredensial login:*\n"
        f"• Username : `{username}`\n"
        f"• Password : `{plain_password}`\n\n"
        f"Silakan login di aplikasi FLIPUS dan segera ganti password Anda.\n"
        f"\n--\nDiundang oleh: {current_user.get('nama_lengkap') or current_user.get('username') or 'admin'}"
    )

    wa_sent = False
    wa_resp_dict: dict = {"status": "skipped", "reason": "send_disabled_or_unknown_error"}
    try:
        from app.services.whatsapp import send_simple_message as _send
        wa_resp_dict = _send(wa, wa_msg)
        wa_sent = isinstance(wa_resp_dict, dict) and wa_resp_dict.get("status") in ("sent", "ok", True)
        if isinstance(wa_resp_dict.get("status"), bool):
            wa_sent = wa_resp_dict.get("status") is True
    except Exception as exc:
        print(f"[M8 invite] WA send error: {exc}", file=sys.stderr, flush=True)
        wa_resp_dict = {"error": str(exc)[:200]}

    # Serialize dict ke JSON string — response_model=InviteUserOut pakai Optional[str]
    import json as _json
    wa_resp_str = _json.dumps(wa_resp_dict, default=str)[:1000]

    return {
        "status": "ok",
        "user_id": new_user.id,
        "username": username,
        "password_plain": plain_password,
        "nama_lengkap": payload.nama_lengkap,
        "role": role,
        "tenant_id": tenant.id,
        "nomor_whatsapp": wa,
        "wa_sent": wa_sent,
        "wa_response": wa_resp_str,
    }


# ===== Endpoint 2: POST /kuitansi/{kuitansi_id}/void =====

@router.post("/kuitansi/{kuitansi_id}/void", response_model=VoidOut)
def void_kuitansi(
    kuitansi_id: int,
    reason: Optional[str] = None,  # query param ?reason=...
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Soft-void Kuitansi (set is_purged=True + audit log).

    Rule:
    - Hanya BENDAHARA di tenant yang sama, ATAU creator user.
    - Hanya boleh void kalau status != 'finalized'. Kalau sudah finalized → 403.
      (Override oleh Auditor bisa manual via DB atau future endpoint.)
    """
    k = db.query(Kuitansi).filter(Kuitansi.id == kuitansi_id).first()
    if not k:
        raise HTTPException(404, "Kuitansi tidak ditemukan")
    if k.is_purged:
        raise HTTPException(400, "Kuitansi sudah void")

    # Tenant check
    caller = current_user
    if k.tenant_id != caller["tenant_id"]:
        raise HTTPException(403, "Kuitansi bukan dari jemaat Anda")

    # RBAC: hanya BENDAHARA atau creator
    is_bendahara = caller["role"] == "BENDAHARA"
    # Tidak ada field created_by di Kuitansi (cek payload_hash untuk creator, fallback ke audit log)
    # Simplifikasi: BENDAHARA saja untuk saat ini (paling aman)
    if not is_bendahara:
        raise HTTPException(403, "Hanya Bendahara yang boleh void Kuitansi")

    # Status check
    if k.status == "finalized":
        raise HTTPException(
            403,
            "Kuitansi sudah final approved. Untuk void, hubungi Auditor Misi (butuh approval khusus).",
        )
    if k.status == "rejected":
        # Sudah ditolak — bukan void, cukup biarkan rejected.
        # Untuk konsistensi, izinkan void agar hilang dari list.
        pass

    from datetime import datetime as _dt
    k.is_purged = True
    audit_action_void = (
        f"VOID_KUI_{k.id}_{k.status[:8]}_u{caller['id']}"
    )[:63]
    db.add(AuditLog(
        tenant_id=k.tenant_id,
        action=audit_action_void,
    ))
    db.commit()

    return VoidOut(
        status="voided",
        entity_type="kuitansi",
        entity_id=k.id,
        nomor=k.nomor_kuitansi,
        voided_by_user_id=caller["id"],
        voided_at=_dt.utcnow().isoformat(),
        reason=reason,
    )


# ===== Endpoint 3: POST /pengeluaran/{pengeluaran_id}/void =====

@router.post("/pengeluaran/{pengeluaran_id}/void", response_model=VoidOut)
def void_pengeluaran(
    pengeluaran_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Soft-void Pengeluaran (set is_purged=True + audit).

    Rule:
    - Hanya BENDAHARA atau creator.
    - Hanya boleh void kalau status in ('draft', 'pending_approval', 'rejected').
      Kalau sudah 'approved' → 403 (locked, butuh Auditor override).
    """
    p = db.query(Pengeluaran).filter(Pengeluaran.id == pengeluaran_id).first()
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.is_purged:
        raise HTTPException(400, "Pengeluaran sudah void")

    if p.tenant_id != current_user["tenant_id"]:
        raise HTTPException(403, "Pengeluaran bukan dari jemaat Anda")

    is_bendahara = current_user["role"] == "BENDAHARA"
    is_creator = (p.created_by_user_id == current_user["id"])
    if not (is_bendahara or is_creator):
        raise HTTPException(403, "Hanya Bendahara atau creator yang boleh void Pengeluaran")

    if p.status == "approved":
        raise HTTPException(
            403,
            "Pengeluaran sudah approved. Untuk void, hubungi Auditor Misi (butuh approval khusus).",
        )
    if p.status == "approved_ketua":
        raise HTTPException(
            403,
            "Pengeluaran sudah disetujui Ketua. Untuk void, hubungi Pendeta atau Auditor.",
        )

    from datetime import datetime as _dt
    p.is_purged = True
    audit_action_void = (
        f"VOID_OUT_{p.id}_{p.status[:8]}_u{current_user['id']}"
    )[:63]
    db.add(AuditLog(
        tenant_id=p.tenant_id,
        action=audit_action_void,
    ))
    db.commit()

    return VoidOut(
        status="voided",
        entity_type="pengeluaran",
        entity_id=p.id,
        nomor=p.nomor_pengeluaran,
        voided_by_user_id=current_user["id"],
        voided_at=_dt.utcnow().isoformat(),
        reason=reason,
    )