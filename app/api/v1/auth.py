"""

Auth: login + JWT issuance + role + license guard (anti-clone, integrated)
+ forgot password endpoint (self-service reset via WA)
+ tenant status guard (Tahap 20 SaaS)
+ login lockout (v1.4 hardening) — 5 attempts → 15 min lock.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import limiter as _rate_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    generate_tenant_signature,
    hash_password,
    utcnow,
    verify_password,
)
from app.models.audit import AuditLog

# FASE 3-S3.S8 — refresh token server-side store.
from app.models.refresh_token import RefreshToken
from app.models.revoked_token import RevokedToken
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tenant_service import slugify
from app.services.whatsapp import send_simple_message
from app.utils.password_gen import generate_random_password, mask_password, validate_password_strength

logger = logging.getLogger(__name__)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

ROLES_3_TIER = {"ADMIN_UNI", "AUDITOR_MISI", "PENDETA", "KETUA_KEUANGAN", "BENDAHARA"}

# T45: Mandatory 2FA untuk role yang punya akses lintas jemaat / level organisasi.
# Role ini paling berisiko kalau kredensial bocor — wajib pakai 2FA.
MANDATORY_2FA_ROLES = {"ADMIN_UNI", "AUDITOR_MISI"}

class LoginIn(BaseModel):
    username: str
    password: str
    tenant_slug: str | None = None  # Tahap 20: optional tenant hint for SaaS
    totp_code: str | None = None  # T23-7: 2FA code (optional, kalau user sudah enable)


class TokenOut(BaseModel):
    """FASE 3-S3.S8 — return both access_token (15 min) AND refresh_token (7 day)."""
    access_token: str
    refresh_token: str  # NEW: long-lived refresh credential (server-side stored)
    token_type: str = "bearer"
    # Access token TTL in seconds (15 min = 900). Client boleh pakai ini untuk
    # schedule refresh (e.g., expire - 60 detik) supaya seamless UX.
    expires_in: int = 900
    role: str
    tenant_id: int
    tenant_slug: str | None = None
    tenant_status: str | None = None


class TwoFactorRequiredOut(BaseModel):
    """Returned ketika user punya 2FA enabled dan belum submit TOTP."""
    requires_2fa: bool = True
    partial_token: str  # short-lived (5 min), submit ke /2fa/login
    username: str


class TwoFactorLoginIn(BaseModel):
    """Step 2: submit TOTP code dengan partial_token."""
    partial_token: str
    totp_code: str
    backup_code: str | None = None  # alternatif kalau TOTP device hilang


class TwoFactorDisableIn(BaseModel):
    """Untuk disable 2FA — require current TOTP untuk konfirmasi."""
    totp_code: str
    password: str


class ForgotPasswordIn(BaseModel):
    """Input boleh username ATAU nomor_whatsapp (auto-detect)."""
    identifier: str  # username OR nomor_wa
    tenant_slug: str | None = None  # Tahap 20: scope forgot-password by tenant

class ForgotPasswordOut(BaseModel):
    status: str  # "sent" / "not_found" / "rate_limited" / "no_wa"
    identifier: str
    message: str
    new_password_masked: str | None = None  # cuma untuk audit (masked)


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
            logger.exception("send_simple_message (admin notify) gagal; audit log tetap dicatat")


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
    token: str | None = Depends(oauth2_scheme),
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
        iat_dt = datetime.fromtimestamp(iat_ts, tz=UTC)
        # Strip tz info dari pwd_changed kalau naive
        if pwd_changed.tzinfo is None:
            pwd_changed = pwd_changed.replace(tzinfo=UTC)
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

    # FASE 3-S3.S1 — update request-scoped contextvars so every subsequent
    # log line emitted during this request carries tenant_id + user_id.
    # (request_id was already set by RequestContextMiddleware.)
    from app.core.logger import tenant_id_var, user_id_var
    tenant_id_var.set(str(user.tenant_id))
    user_id_var.set(str(user.id))

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


@router.post("/login", tags=['Auth'])
@_rate_limiter.limit("10/minute")  # FASE 3 K1: anti-brute-force per-IP
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
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
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, 'Gagal decrypt TOTP secret') from None
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
            # FASE 3-S3.S8 — issue BOTH access (15-min) AND refresh (7-day) tokens.
            access = create_access_token({
                "sub": user.id,
                "role": user.role,
                "tenant_id": user.tenant_id,
            })
            refresh = create_refresh_token({
                "sub": user.id,
                "role": user.role,
                "tenant_id": user.tenant_id,
            })
            _persist_refresh_token(db, refresh, user, request)
            return TokenOut(
                access_token=access,
                refresh_token=refresh,
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

    # FASE 3-S3.S8 — issue both tokens (legacy no-2FA path).
    access = create_access_token({
        "sub": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
    })
    refresh = create_refresh_token({
        "sub": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
    })
    _persist_refresh_token(db, refresh, user, request)
    return TokenOut(
        access_token=access,
        refresh_token=refresh,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=user_tenant.slug,
        tenant_status=user_tenant.status,
    )


# ===== FASE 3-S3.S8 — refresh token helpers =====

def _client_ip(request: Request) -> str:
    """Extract client IP (X-Forwarded-For aware, sama dengan auth.py lain)."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _persist_refresh_token(db: Session, refresh_jwt: str, user: User, request: Request) -> None:
    """Simpan refresh token JTI ke tabel RefreshToken.

    Dipanggil setiap kali login / refresh issue token baru. Kalau duplicate
    (misalnya race condition), commit akan raise IntegrityError — kita catch
    supaya tidak crash endpoint login user.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        payload = decode_access_token(refresh_jwt) or {}
    except Exception:
        payload = {}
    jti = payload.get("jti")
    exp_ts = payload.get("exp")
    if not jti or not exp_ts:
        return  # defensive — tidak bisa store tanpa JTI/exp
    expires_at = datetime.fromtimestamp(exp_ts, tz=UTC)
    row = RefreshToken(
        jti=jti,
        user_id=user.id,
        tenant_id=user.tenant_id,
        expires_at=expires_at,
        created_ip=_client_ip(request),
        created_user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        # JTI sudah ada (race) — rollback agar session bersih, tidak propagate.
        db.rollback()


@router.post("/forgot-password", tags=['Auth'], response_model=ForgotPasswordOut)
@_rate_limiter.limit("3/minute")  # FASE 3 K1: anti-enumeration per-IP
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

    # T78 (diganti FASE 3 K1): Rate-limit per IP untuk cegah username enumeration.
    # Sebelumnya pakai in-memory dict (process-local). Sekarang slowapi @limiter.limit("3/minute")
    # di atas yang handle — Redis-ready jika pindah ke multi-worker (lihat app/core/rate_limiter.py).
    client_ip = request.client.host if request.client else "unknown"
    # FASE 3-S2.T4: audit log ENHANCED dengan IP + UA untuk forensic investigation.
    xff_header = request.headers.get("x-forwarded-for", "")
    if xff_header:
        first_xff = xff_header.split(",")[0].strip()
        client_ip = client_ip + " (xff=" + first_xff + ")"
    ua = request.headers.get("user-agent", "unknown")[:200]

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
        payload_hash="{}|ip={}|ua={}".format(user.id, client_ip, ua)[:64],
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
        payload_hash="{}|ip={}|ua={}".format(user.id, client_ip, ua)[:64],
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


# ===== FASE 3-S3.S8 — refresh token endpoints =====

class RefreshIn(BaseModel):
    """Body untuk POST /auth/refresh. Client kirim refresh_token dari login/refresh sebelumnya."""
    refresh_token: str


@router.post("/refresh", tags=['Auth'], response_model=TokenOut)
@_rate_limiter.limit("30/minute")
def refresh(
    data: RefreshIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """FASE 3-S3.S8 — Exchange refresh token untuk access token baru + new refresh (rotation).

    Flow:
      1. Decode JWT → verifikasi signature + cek typ="refresh"
      2. Cari RefreshToken row by JTI
         - kalau tidak ada → 401 (token not issued by us / forged)
         - kalau revoked_at ≠ None → 401
         - kalau used_at ≠ None → DETEKSI REUSE → revoke seluruh chain user
      3. Verify user masih ada & aktif
      4. Mark old row used_at=now()
      5. Issue new access (15-min) + new refresh (7-day)
      6. Persist new refresh row
      7. Return TokenOut
    """
    payload = decode_access_token(data.refresh_token)
    if not payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token (signature / format)",
        )
    # Anti privilege-escalation: jangan boleh kirim access token sebagai refresh.
    if payload.get("typ") != "refresh":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Token type salah: typ={payload.get('typ')!r}, diharapkan 'refresh'",
        )

    jti = payload.get("jti")
    sub = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not jti or not sub:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token tidak punya JTI/sub (legacy token?)",
        )

    rt = db.query(RefreshToken).filter(RefreshToken.jti == jti).first()
    if not rt:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not recognized",
        )
    if rt.revoked_at is not None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token sudah di-revoke: {rt.revoked_reason}",
        )

    if rt.used_at is not None:
        # Reuse detection — kemungkinan token dicuri. Revoke seluruh chain.
        all_rt = db.query(RefreshToken).filter(
            RefreshToken.user_id == rt.user_id,
            RefreshToken.revoked_at.is_(None),
        ).all()
        for r in all_rt:
            r.revoked_at = datetime.now(UTC)
            r.revoked_reason = "reuse_detected"
        db.add(AuditLog(
            tenant_id=rt.tenant_id,
            action=f"REFRESH_REUSE_DETECTED_user_{rt.user_id}_revoked_{len(all_rt)}",
            payload_hash=jti[:32],
        ))
        db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token sudah dipakai. Semua sesi direvoke. Silakan login ulang.",
        )

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="User account sudah non-aktif",
        )
    if user.tenant_id != tenant_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Tenant mismatch in refresh token",
        )

    # SUCCESS — rotate.
    rt.used_at = datetime.now(UTC)
    rt.redeemed_ip = _client_ip(request)
    rt.redeemed_user_agent = (request.headers.get("user-agent") or "")[:255]

    new_access = create_access_token({
        "sub": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
    })
    new_refresh = create_refresh_token({
        "sub": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id,
    })
    _persist_refresh_token(db, new_refresh, user, request)

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        action=f"REFRESH_OK_user_{user.id}_rotated_{jti[:12]}",
        payload_hash=user.username,
    ))
    db.commit()

    user_tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return TokenOut(
        access_token=new_access,
        refresh_token=new_refresh,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=user_tenant.slug if user_tenant else None,
        tenant_status=user_tenant.status if user_tenant else None,
    )


@router.post("/logout", tags=['Auth'], response_model=LogoutOut)
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
    expires_at = datetime.fromtimestamp(exp_ts, tz=UTC) if exp_ts else datetime.now(UTC) + timedelta(hours=24)

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

    # FASE 3-S3.S8 — kalau access token dipakai, revoke semua refresh token
    # aktif milik user ini (semantik logout-all). Untuk logout per-device,
    # client harus kirim refresh_token eksplisit (planned v1.6).
    rt_rows = db.query(RefreshToken).filter(
        RefreshToken.user_id == current["id"],
        RefreshToken.revoked_at.is_(None),
        RefreshToken.used_at.is_(None),
    ).all()
    for rt in rt_rows:
        rt.revoked_at = datetime.now(UTC)
        rt.revoked_reason = "logout_access_token"

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"LOGOUT_user_{current['id']}_rt_revoked={len(rt_rows)}",
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


@router.post("/change-password", tags=['Auth'], response_model=ChangePasswordOut)
def change_password(
    data: ChangePasswordIn,
    request: Request,
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
    5. Audit log (T4 — enhanced dengan IP address + user-agent untuk forensic) + notify WA ke user (best-effort)
    """
    from app.core.security import hash_password, verify_password

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
    user.last_password_change_at = datetime.now(UTC)

    # 5) Auto-revoke semua token user ini (logout semua device)
    # Catatan: tidak punya list JTI — solusi: tambah kolom user_id ke revoked_tokens
    # tapi jti SUDAH ada foreign key user_id. Pakai pendekatan berbeda:
    # increment "token_epoch" di user, dan validasi token mengandung epoch matching.
    # Untuk simplicity v1.5-D: pakai password_changed_at sebagai invalidation timestamp.
    # Token yang iat < password_changed_at akan ditolak di get_current_user.
    user.password_changed_at = datetime.now(UTC)

    # FASE 3-S2.T4 — Audit log ENHANCED dengan IP + UA untuk forensic.
    # Audit log ini penting kalau akun dibajak — attacker biasanya ganti password
    # supaya korban tidak bisa login & tidak bisa reset. Dengan IP + UA, admin
    # bisa cek: "apakah perubahan ini dari IP/lokasi yang biasa dipakai user?"
    client_ip = request.client.host if request.client else "unknown"
    # Perhatikan X-Forwarded-For kalau di belakang reverse proxy (nginx/cloudflare).
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        client_ip = f"{client_ip} (xff={xff.split(',')[0].strip()})"
    ua = request.headers.get("user-agent", "unknown")[:200]

    db.add(AuditLog(
        tenant_id=user.tenant_id,
        action=f"PASSWORD_CHANGED_user_{user.id}",
        payload_hash=f"{user.username}|ip={client_ip}|ua={ua}",
    ))
    db.commit()

    # 6) Notify user via WA (best-effort — kalau gagal tetap success)
    if user.nomor_whatsapp:
        try:
            from app.services.whatsapp import send_simple_message
            send_simple_message(
                target=user.nomor_whatsapp,
                message=(
                    f"🔐 Password FLIPUS Anda telah diganti pada {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}.\n"
                    f"Semua session lama otomatis logout. "
                    f"Jika ini BUKAN Anda, hubungi Admin Uni SEGERA."
                ),
            )
        except Exception:
            logger.exception("send_simple_message (change-password notify) gagal")  # best-effort

    return ChangePasswordOut(
        status="ok",
        message="Password berhasil diganti. Semua session lama otomatis logout.",
    )
