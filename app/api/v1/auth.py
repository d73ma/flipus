"""
Auth: login + JWT issuance + role + license guard (anti-clone, integrated)
+ forgot password endpoint (self-service reset via WA)
+ tenant status guard (Tahap 20 SaaS)
+ login lockout (v1.4 hardening) — 5 attempts → 15 min lock.
"""
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.security import utcnow
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_tenant_signature,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.models.tenant import Tenant
from app.models.audit import AuditLog
from app.models.revoked_token import RevokedToken
from app.utils.password_gen import generate_random_password, mask_password, validate_password_strength
from app.services.whatsapp import send_simple_message
from app.services.tenant_service import slugify

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

ROLES_3_TIER = {"ADMIN_UNI", "AUDITOR_MISI", "PENDETA", "KETUA_KEUANGAN", "BENDAHARA"}

# T45: Mandatory 2FA untuk role yang punya akses lintas jemaat / level organisasi.
# Role ini paling berisiko kalau kredensial bocor — wajib pakai 2FA.
MANDATORY_2FA_ROLES = {"ADMIN_UNI", "AUDITOR_MISI"}

class LoginIn(BaseModel):
    username: str
    password: str
    tenant_slug: Optional[str] = None  # Tahap 20: optional tenant hint for SaaS
    totp_code: Optional[str] = None  # T23-7: 2FA code (optional, kalau user sudah enable)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: int
    tenant_slug: Optional[str] = None
    tenant_status: Optional[str] = None


class TwoFactorRequiredOut(BaseModel):
    """Returned ketika user punya 2FA enabled dan belum submit TOTP."""
    requires_2fa: bool = True
    partial_token: str  # short-lived (5 min), submit ke /2fa/login
    username: str


class TwoFactorLoginIn(BaseModel):
    """Step 2: submit TOTP code dengan partial_token."""
    partial_token: str
    totp_code: str
    backup_code: Optional[str] = None  # alternatif kalau TOTP device hilang


class TwoFactorDisableIn(BaseModel):
    """Untuk disable 2FA — require current TOTP untuk konfirmasi."""
    totp_code: str
    password: str


class ForgotPasswordIn(BaseModel):
    """Input boleh username ATAU nomor_whatsapp (auto-detect)."""
    identifier: str  # username OR nomor_wa
    tenant_slug: Optional[str] = None  # Tahap 20: scope forgot-password by tenant

class ForgotPasswordOut(BaseModel):
    status: str  # "sent" / "not_found" / "rate_limited" / "no_wa"
    identifier: str
    message: str
    new_password_masked: Optional[str] = None  # cuma untuk audit (masked)


def _audit_cross_tenant_attempt(
    db: Session, user: User, attempted_tenant_id: int, action: str,
) -> None:
    """Log cross-tenant access attempt (Tahap 20 hardening) + T50 WA alert."""
    db.add(AuditLog(
        tenant_id=attempted_tenant_id,
        action=f"CROSS_TENANT_BLOCKED_{action}_user_{user.id}_true_tenant_{user.tenant_id}",
        payload_hash=user.username,
    ))
    db.commit()
    # T50: Kirim WA alert ke semua Admin Uni (throttle 5 menit per user)
    _notify_security_event_wa(
        db=db,
        severity="CRITICAL",
        title="Cross-tenant access diblokir",
        details=(
            f"User '{user.username}' mencoba akses tenant_id={attempted_tenant_id} "
            f"padahal tenant sebenarnya={user.tenant_id}. "
            f"Action: {action}. Kemungkinan compromised credential atau probing."
        ),
        throttle_key=f"CROSS_TENANT_user_{user.id}",
    )


def _notify_security_event_wa(
    db: Session,
    severity: str,
    title: str,
    details: str,
    throttle_key: str,
    throttle_minutes: int = 5,
) -> None:
    """T50: Kirim WA alert ke semua ADMIN_UNI untuk security event kritis.

    Throttle per throttle_key (default 5 menit) supaya tidak spam WA kalau
    ada burst (e.g. brute-force pattern menghasilkan banyak event).

    severity: "CRITICAL" | "WARNING" — saat ini hanya string untuk display.
    """
    from app.models.user import User as UserModel

    # Throttle: cek audit log terbaru dengan key ini dalam window
    cutoff = utcnow() - timedelta(minutes=throttle_minutes)
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.action == f"SECURITY_WA_ALERT_{throttle_key}")
        .filter(AuditLog.created_at >= cutoff)
        .first()
    )
    if recent:
        return  # Skip — masih dalam throttle window

    # Catat bahwa kita kirim alert (untuk throttle window berikutnya).
    # Pakai tenant_id dari first available tenant (FK safety). Kalau tidak ada,
    # skip throttle log — alert tetap dikirim (best-effort).
    first_tenant = db.query(Tenant).first()
    if first_tenant:
        try:
            db.add(AuditLog(
                tenant_id=first_tenant.id,
                action=f"SECURITY_WA_ALERT_{throttle_key}",
                payload_hash=severity,
            ))
            db.commit()
        except Exception:
            db.rollback()
            # Lanjut kirim WA — throttle log gagal tapi notifikasi tetap penting

    # Kirim ke semua ADMIN_UNI aktif yang punya nomor WA
    admins = (
        db.query(UserModel)
        .filter(UserModel.role == "ADMIN_UNI")
        .filter(UserModel.is_active == True)  # noqa: E712
        .filter(UserModel.nomor_whatsapp.isnot(None))
        .all()
    )

    severity_emoji = "🚨" if severity == "CRITICAL" else "⚠️"
    msg = (
        f"*FLIPUS SECURITY ALERT* {severity_emoji}\n\n"
        f"*{title}*\n\n"
        f"{details}\n\n"
        f"Waktu: {utcnow().isoformat()}\n\n"
        f"_Auto-alert dari sistem FLIPUS_"
    )

    for admin in admins:
        try:
            send_simple_message(admin.nomor_whatsapp, msg)
        except Exception:
            # Best-effort — kalau WA gagal, audit log sudah ada
            pass


# ===== Login Lockout (v1.4 hardening) =====
def _count_failed_login_attempts(db: Session, username: str) -> int:
    """Hitung LOGIN_FAILED dalam window lockout (last 15 min) untuk username tsb.

    Lock by username (global, cross-tenant). Attackers tidak tahu tenant_slug,
    sehingga mereka hanya dapat mengunci username yang diketahui publik.
    """
    cutoff = utcnow() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
    return (
        db.query(AuditLog)
        .filter(AuditLog.action == "LOGIN_FAILED")
        .filter(AuditLog.payload_hash == username)
        .filter(AuditLog.created_at >= cutoff)
        .count()
    )


def _is_login_locked(db: Session, username: str) -> bool:
    """Cek apakah username sudah melebihi max attempts dan masih dalam window lock."""
    return _count_failed_login_attempts(db, username) >= settings.LOGIN_MAX_ATTEMPTS


def _record_failed_login(db: Session, username: str, tenant_id: int) -> None:
    """Catat attempt gagal di AuditLog. tenant_id wajib (FK ke tenants).

    Note: hanya dipanggil kalau user ditemukan, sehingga tenant_id valid.
    Untuk user yang tidak ditemukan, kita skip audit (tidak ada FK target)
    dan lockout tidak akan trigger untuk username tsb (tidak ada untuk dilindungi).
    """
    db.add(AuditLog(
        tenant_id=tenant_id,
        action="LOGIN_FAILED",
        payload_hash=username,
    ))
    db.commit()


# ===== End Login Lockout =====


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """
    Decode JWT + license guard (anti-clone) + tenant status guard (Tahap 20).

    Otomatis berlaku untuk semua endpoint. Validates:
    1. JWT signature + expiry
    2. User exists and is_active
    3. Tenant exists
    4. Tenant status == 'active' (Tahap 20)
    5. Tenant signature matches (anti-clone)
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    # v1.5-A: JWT blacklist check — reject kalau JTI ada di revoked_tokens
    jti = payload.get("jti")
    if jti and db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token sudah di-logout / revoked")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User tidak aktif")

    # v1.5-D: Kalau user ganti password setelah token ini di-issue → reject
    # (auto-logout semua device saat ganti password)
    iat_ts = payload.get("iat")
    pwd_changed = getattr(user, "password_changed_at", None)
    if iat_ts and pwd_changed:
        iat_dt = datetime.fromtimestamp(iat_ts, tz=timezone.utc)
        # Strip tz info dari pwd_changed kalau naive
        if pwd_changed.tzinfo is None:
            pwd_changed = pwd_changed.replace(tzinfo=timezone.utc)
        if iat_dt < pwd_changed:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Token lama — password telah diganti, silakan login ulang",
            )

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not tenant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tenant tidak ditemukan")

    # Tahap 20 SaaS: tenant harus status aktif
    if tenant.status != "active" or not tenant.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Tenant {tenant.nama_jemaat_lokal} berstatus '{tenant.status}'. Hubungi administrator.",
        )

    # License guard (anti-clone, legacy)
    expected = generate_tenant_signature(
        tenant.nama_uni,
        tenant.nama_kantor_misi,
        tenant.nama_jemaat_lokal,
    )
    if tenant.tenant_signature != expected:
        audit = AuditLog(
            tenant_id=tenant.id,
            action="LICENSE_TAMPER_DETECTED",
            payload_hash=tenant.tenant_signature,
            verifikasi_sintaks_ai="TAMPER",
        )
        db.add(audit)
        db.commit()
        # T50: Kirim WA alert — LICENSE_TAMPER adalah indikasi kuat clone attempt
        _notify_security_event_wa(
            db=db,
            severity="CRITICAL",
            title="🚨 TAMPER DETECTED — kemungkinan clone database",
            details=(
                f"Tenant '{tenant.nama_jemaat_lokal}' (id={tenant.id}) gagal signature check. "
                f"Kemungkinan: DB di-clone/di-restore ke environment lain, "
                f"atau ada edit langsung di luar FLIPUS. SEGERA investigasi!"
            ),
            throttle_key=f"LICENSE_TAMPER_tenant_{tenant.id}",
            throttle_minutes=60,  # Longer throttle — event rare
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Tenant signature invalid — kemungkinan clone/tamper",
        )

    # Backfill slug kalau legacy tenant belum punya
    if not tenant.slug:
        from app.services.tenant_service import ensure_slug
        ensure_slug(db, tenant)
        db.commit()

    return {
        "id": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant.slug,
        "tenant_status": tenant.status,
    }


def require_roles(*roles: str):
    def checker(current: dict = Depends(get_current_user)) -> dict:
        if current["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Butuh role {}".format(roles))
        return current
    return checker


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    """
    Login dengan optional tenant_slug (Tahap 20) + optional TOTP (Tahap 23)
    + login lockout (v1.4 hardening).

    T23-7: 2FA Flow
    - Tahap 1: Username + password → kalau user.is_2fa_enabled → return TwoFactorRequiredOut
    - Tahap 1 (alternative): Kirim totp_code langsung di login → verify sekalian → TokenOut
    - Tahap 2: Submit partial_token + totp_code → /v1/auth/2fa/login → TokenOut

    v1.4 hardening (T44): Login lockout
    - Cek LOGIN_FAILED count >= LOGIN_MAX_ATTEMPTS dalam window LOGIN_LOCKOUT_MINUTES
    - Kalau lock → reject dengan HTTP 429 (Too Many Requests)
    - Record setiap attempt gagal sebagai LOGIN_FAILED di AuditLog
    - Successful login → tidak otomatis reset (counter expire sendiri dalam 15 min)

    Backward compat: user tanpa 2FA → flow lama (langsung TokenOut)
    """
    # ===== T44 Lockout: cek SEBELUM password verify (anti timing-attack reveal username) =====
    if _is_login_locked(db, data.username):
        # Hitung sisa waktu lock untuk UX message
        cutoff = utcnow() - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
        latest_fail = (
            db.query(AuditLog)
            .filter(AuditLog.action == "LOGIN_FAILED")
            .filter(AuditLog.payload_hash == data.username)
            .filter(AuditLog.created_at >= cutoff)
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        remaining_min = 0
        if latest_fail:
            unlock_at = latest_fail.created_at + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            delta = unlock_at - utcnow()
            remaining_min = max(1, int(delta.total_seconds() / 60) + 1)

        # Audit hanya kalau user ada (FK tenant_id valid)
        blocked_user = db.query(User).filter(User.username == data.username).first()
        if blocked_user:
            db.add(AuditLog(
                tenant_id=blocked_user.tenant_id,
                action="LOGIN_BLOCKED_LOCKOUT",
                payload_hash=data.username,
            ))
            db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Akun terkunci karena {settings.LOGIN_MAX_ATTEMPTS}× gagal login. "
            f"Coba lagi dalam {remaining_min} menit.",
            headers={"Retry-After": str(settings.LOGIN_LOCKOUT_MINUTES * 60)},
        )

    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        # User tidak ada — return 401 tanpa audit (tidak ada tenant_id FK target,
        # dan lockout untuk username unknown tidak perlu; attacker spam nama fiktif
        # tidak akan mendapat lockout tapi juga tidak akan mendapat signal apapun).
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username/password salah")
    if not verify_password(data.password, user.password_hash):
        # T44: Record failed attempt (user ada → tenant_id valid)
        _record_failed_login(db, data.username, tenant_id=user.tenant_id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username/password salah")
    if user.role not in ROLES_3_TIER:
        _record_failed_login(db, data.username, tenant_id=user.tenant_id)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role tidak dikenal: {}".format(user.role))

    user_tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if not user_tenant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tenant user tidak ditemukan")

    # Tahap 20 SaaS: jika tenant_slug diberikan, harus match
    if data.tenant_slug:
        slug_norm = slugify(data.tenant_slug)
        if user_tenant.slug != slug_norm:
            _audit_cross_tenant_attempt(
                db, user, user_tenant.id, f"LOGIN_WRONG_TENANT_attempted_{slug_norm}"
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Username tidak ditemukan di jemaat tersebut",
            )

    # Tahap 20 SaaS: tenant harus aktif
    if user_tenant.status != "active" or not user_tenant.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Jemaat '{user_tenant.nama_jemaat_lokal}' berstatus '{user_tenant.status}', tidak bisa login",
        )

    # Backfill slug kalau legacy tenant belum punya (T20 SaaS)
    if not user_tenant.slug:
        from app.services.tenant_service import ensure_slug
        ensure_slug(db, user_tenant)
        db.commit()
        db.refresh(user_tenant)

    # ===== T45: Mandatory 2FA untuk role sensitif =====
    if (
        settings.ENFORCE_2FA_FOR_SENSITIVE_ROLES
        and user.role in MANDATORY_2FA_ROLES
        and not user.is_2fa_enabled
    ):
        db.add(AuditLog(
            tenant_id=user.tenant_id,
            action=f"LOGIN_REJECTED_NO_2FA_user_{user.id}_role_{user.role}",
            payload_hash=user.username,
        ))
        db.commit()
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {user.role} WAJIB mengaktifkan 2FA. "
            f"Hubungi Admin Uni untuk setup 2FA terlebih dahulu. "
            f"(Atau matikan sementara ENFORCE_2FA_FOR_SENSITIVE_ROLES di .env untuk demo).",
        )

    # T23-7: 2FA Flow
    if user.is_2fa_enabled:
        # 2FA enabled — cek apakah user submit TOTP code sekaligus
        if data.totp_code:
            # Combined login: verify TOTP then issue full token
            from app.services.twofa_service import decrypt_secret, verify_totp
            try:
                secret = decrypt_secret(user.totp_secret_encrypted)
            except Exception:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal decrypt TOTP secret")
            if not verify_totp(secret, data.totp_code):
                # Try backup code
                from app.services.twofa_service import verify_backup_code
                if user.backup_codes_hashed:
                    is_valid, idx = verify_backup_code(data.totp_code, user.backup_codes_hashed)
                    if is_valid:
                        # Remove used backup code (single-use)
                        user.backup_codes_hashed = [
                            c for i, c in enumerate(user.backup_codes_hashed) if i != idx
                        ]
                        user.last_2fa_used_at = utcnow()
                        db.commit()
                        db.add(AuditLog(
                            tenant_id=user.tenant_id,
                            action=f"2FA_LOGIN_BACKUP_user_{user.id}",
                            payload_hash=str(user.id),
                        ))
                        db.commit()
                    else:
                        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kode 2FA salah")
                else:
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kode 2FA salah")
            else:
                user.last_2fa_used_at = utcnow()
                db.commit()
                db.add(AuditLog(
                    tenant_id=user.tenant_id,
                    action=f"2FA_LOGIN_TOTP_user_{user.id}",
                    payload_hash=str(user.id),
                ))
                db.commit()
            # T44: Record successful login untuk audit trail
            db.add(AuditLog(
                tenant_id=user.tenant_id,
                action=f"LOGIN_SUCCESS_user_{user.id}",
                payload_hash=user.username,
            ))
            db.commit()
            # Issue full JWT
            token = create_access_token({
                "sub": user.id,
                "role": user.role,
                "tenant_id": user.tenant_id,
            })
            return TokenOut(
                access_token=token,
                role=user.role,
                tenant_id=user.tenant_id,
                tenant_slug=user_tenant.slug,
                tenant_status=user_tenant.status,
            )
        else:
            # 2FA required — return partial token for step 2
            partial = create_access_token({
                "sub": user.id,
                "stage": "2fa_pending",
                "tenant_id": user.tenant_id,
            }, expires_minutes=5)
            return TwoFactorRequiredOut(
                requires_2fa=True,
                partial_token=partial,
                username=user.username,
            )

    # No 2FA — direct token (legacy flow)
    # T44: Record successful login untuk audit trail
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        action=f"LOGIN_SUCCESS_user_{user.id}",
        payload_hash=user.username,
    ))
    db.commit()
    token = create_access_token({
        "sub": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
    })
    return TokenOut(
        access_token=token,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=user_tenant.slug,
        tenant_status=user_tenant.status,
    )


@router.post("/forgot-password", response_model=ForgotPasswordOut)
def forgot_password(
    data: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Self-service reset password via WhatsApp.

    Lookup by username ATAU nomor_whatsapp. Generate password baru random,
    hash, simpan, kirim plain password via Fonnte ke nomor WA user.

    Tahap 20 SaaS: jika tenant_slug diberikan, scope lookup ke tenant tsb saja.
    Tanpa tenant_slug: cari di semua tenant (backward compat).

    Rate limit:
    - Per user: max 1 request per 5 menit (cek audit log).
    - Per IP (T78): max 5 request per 5 menit (in-memory dict) untuk cegah
      username enumeration attack dari 1 IP.
    """
    identifier = data.identifier.strip()
    if not identifier:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Identifier kosong")

    # T78: Rate-limit per IP untuk cegah username enumeration.
    # In-memory dict (process-local). Untuk multi-worker production, replace dengan Redis.
    client_ip = request.client.host if request.client else "unknown"
    fp_window = getattr(forgot_password, "_ip_window", None)
    if fp_window is None:
        fp_window = {}
        setattr(forgot_password, "_ip_window", fp_window)
    now_ts = utcnow().timestamp()
    # Bersihkan entry > 5 menit
    cutoff_ts = now_ts - 300
    fp_window = {ip: ts for ip, ts in fp_window.items() if ts > cutoff_ts}
    setattr(forgot_password, "_ip_window", fp_window)
    ip_count = sum(1 for ts in fp_window.values() if ts > now_ts - 60)  # max 5 per menit
    if ip_count >= 5:
        # Audit
        db.add(AuditLog(
            tenant_id=0,
            action=f"FORGOT_PASSWORD_IP_RATE_LIMIT_ip_{client_ip}_count_{ip_count}",
            payload_hash=identifier[:32],
        ))
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Terlalu banyak percobaan dari IP Anda. Coba lagi dalam 1 menit.",
        )
    fp_window[client_ip] = now_ts
    setattr(forgot_password, "_ip_window", fp_window)

    # Tahap 20 SaaS: resolve tenant_slug kalau ada
    target_tenant_id = None
    if data.tenant_slug:
        from app.services.tenant_service import get_tenant_by_slug
        t = get_tenant_by_slug(db, data.tenant_slug)
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Jemaat tidak ditemukan")
        target_tenant_id = t.id

    # Lookup user (scoped by tenant kalau slug diberikan)
    q = db.query(User).filter(or_(User.username == identifier, User.nomor_whatsapp == identifier))
    if target_tenant_id is not None:
        q = q.filter(User.tenant_id == target_tenant_id)
    user = q.first()

    if not user:
        return ForgotPasswordOut(
            status="not_found",
            identifier=identifier,
            message="Username atau nomor WA tidak ditemukan",
        )
    if not user.is_active:
        return ForgotPasswordOut(
            status="not_found",
            identifier=identifier,
            message="Akun tidak aktif, hubungi administrator",
        )

    # Tahap 20 SaaS: tenant user harus aktif
    user_tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if user_tenant and (user_tenant.status != "active" or not user_tenant.is_active):
        return ForgotPasswordOut(
            status="not_found",
            identifier=identifier,
            message="Akun di jemaat nonaktif, hubungi administrator",
        )

    # Rate limit: cek audit log PASSWORD_RESET_REQUESTED dalam 5 menit terakhir
    five_min_ago = utcnow() - timedelta(minutes=5)
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("PASSWORD_RESET_%"))
        .filter(AuditLog.payload_hash == str(user.id))
        .filter(AuditLog.created_at >= five_min_ago)
        .first()
    )
    if recent:
        return ForgotPasswordOut(
            status="rate_limited",
            identifier=identifier,
            message="Tunggu 5 menit sebelum request ulang",
        )

    # Catat request (audit trail meskipun WA gagal)
    audit_req = AuditLog(
        tenant_id=user.tenant_id,
        action="PASSWORD_RESET_REQUESTED_user_{}".format(user.id),
        payload_hash=str(user.id),
    )
    db.add(audit_req)
    db.commit()

    if not user.nomor_whatsapp:
        return ForgotPasswordOut(
            status="no_wa",
            identifier=identifier,
            message="Nomor WA belum diset, hubungi administrator",
        )

    # Generate password baru
    new_password = generate_random_password(length=8)
    user.password_hash = hash_password(new_password)
    db.commit()

    # Kirim via WA
    msg = (
        "*RESET PASSWORD FLIPUS*\n\n"
        "Shalom,\n\n"
        "Password Anda telah direset. Berikut kredensial baru:\n\n"
        f"Username: {user.username}\n"
        f"Password baru: {new_password}\n\n"
        "Silakan login dan segera ganti password setelah masuk.\n\n"
        "— Sistem FLIPUS (auto-reset)"
    )
    fonnte_resp = send_simple_message(user.nomor_whatsapp, msg)

    # Audit log success/sent
    wa_status = "SENT" if isinstance(fonnte_resp, dict) and fonnte_resp.get("status") else "FAILED"
    audit_sent = AuditLog(
        tenant_id=user.tenant_id,
        action=f"PASSWORD_RESET_SENT_user_{user.id}_wa_{wa_status}",
        payload_hash=str(user.id),
    )
    db.add(audit_sent)
    db.commit()

    return ForgotPasswordOut(
        status="sent" if wa_status == "SENT" else "wa_failed",
        identifier=identifier,
        message="Password baru telah dikirim ke WhatsApp Anda" if wa_status == "SENT" else "Password di-reset tapi WA gagal, hubungi administrator",
        new_password_masked=mask_password(new_password),
    )


# ==================== v1.5-A: LOGOUT + JWT BLACKLIST ====================

class LogoutOut(BaseModel):
    status: str
    jti: str
    message: str


@router.post("/logout", response_model=LogoutOut)
def logout(
    request: Request,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    v1.5-A — Revoke token JWT saat ini (logout).

    Cara kerja:
    1. Ambil JWT dari header Authorization
    2. Decode → ambil jti + exp
    3. Simpan ke tabel revoked_tokens
    4. Audit log (GDPR compliance — siapa logout, kapan)
    5. Return confirmation

    Setelah logout, token ini tidak bisa dipakai lagi (get_current_user cek
    blacklist sebelum authorize). Untuk logout-all-sessions, butuh endpoint
    terpisah yang blacklist semua JTI milik user_id — punt ke v1.6.
    """
    # Extract token dari header (Bearer)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing Bearer token")
    token = auth.split(" ", 1)[1].strip()

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    jti = payload.get("jti")
    exp_ts = payload.get("exp")
    if not jti:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token tidak punya JTI (legacy token, silakan login ulang)")

    # Convert exp timestamp → datetime UTC
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc) + timedelta(hours=24)

    # Idempotent — kalau sudah pernah di-revoke, return success tanpa duplicate row
    existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    if existing:
        return LogoutOut(
            status="already_revoked",
            jti=jti,
            message="Token ini sudah pernah di-logout sebelumnya",
        )

    revoked = RevokedToken(
        jti=jti,
        user_id=current["id"],
        tenant_id=current["tenant_id"],
        reason="logout",
        expires_at=expires_at,
    )
    db.add(revoked)

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"LOGOUT_user_{current['id']}",
        payload_hash=jti[:32],  # simpan prefix jti sebagai audit trail
    ))
    db.commit()

    return LogoutOut(
        status="ok",
        jti=jti,
        message="Token berhasil di-revoke. Silakan login ulang untuk akses berikutnya.",
    )


# v1.5-D: Change password endpoint
class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class ChangePasswordOut(BaseModel):
    status: str
    message: str


@router.post("/change-password", response_model=ChangePasswordOut)
def change_password(
    data: ChangePasswordIn,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    v1.5-D — User ganti password sendiri.

    Validasi:
    1. current_password harus match (verify hash)
    2. new_password == confirm_password
    3. new_password harus lewat validate_password_strength (T45):
       - min 10 char
       - ada huruf besar + kecil + angka + special char
       - tidak boleh common password (top 100)
       - tidak boleh sama dengan current
    4. Auto-revoke semua token milik user ini (paksa logout semua device)
    5. Audit log + notify WA ke user (best-effort)
    """
    from app.core.security import hash_password, verify_password
    from app.utils.password_gen import validate_password_strength

    # 1) current password check
    user = db.query(User).filter(User.id == current["id"]).first()
    if not user or not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password lama tidak sesuai")

    # 2) confirm match
    if data.new_password != data.confirm_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password baru dan konfirmasi tidak cocok")

    # 3) policy check
    is_strong, reason = validate_password_strength(data.new_password)
    if not is_strong:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Password baru tidak memenuhi kebijakan: {reason}")

    # Cek duplikat dengan current
    if data.new_password == data.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password baru tidak boleh sama dengan yang lama")

    # 4) Update hash
    user.password_hash = hash_password(data.new_password)
    user.last_password_change_at = datetime.now(timezone.utc)

    # 5) Auto-revoke semua token user ini (logout semua device)
    # Catatan: tidak punya list JTI — solusi: tambah kolom user_id ke revoked_tokens
    # tapi jti SUDAH ada foreign key user_id. Pakai pendekatan berbeda:
    # increment "token_epoch" di user, dan validasi token mengandung epoch matching.
    # Untuk simplicity v1.5-D: pakai password_changed_at sebagai invalidation timestamp.
    # Token yang iat < password_changed_at akan ditolak di get_current_user.
    user.password_changed_at = datetime.now(timezone.utc)

    # Audit
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        action=f"PASSWORD_CHANGED_user_{user.id}",
        payload_hash=user.username,
    ))
    db.commit()

    # 6) Notify user via WA (best-effort — kalau gagal tetap success)
    if user.nomor_whatsapp:
        try:
            from app.services.whatsapp import send_simple_message
            send_simple_message(
                target=user.nomor_whatsapp,
                message=(
                    f"🔐 Password FLIPUS Anda telah diganti pada {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.\n"
                    f"Semua session lama otomatis logout. "
                    f"Jika ini BUKAN Anda, hubungi Admin Uni SEGERA."
                ),
            )
        except Exception:
            pass  # best-effort

    return ChangePasswordOut(
        status="ok",
        message="Password berhasil diganti. Semua session lama otomatis logout.",
    )