from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet, InvalidToken
import hashlib

from fastapi import Header, HTTPException, Request, status as _status

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
fernet = Fernet(settings.PII_ENCRYPTION_KEY.encode())


def utcnow() -> datetime:
    """Timezone-aware UTC now. Replacement for deprecated datetime.utcnow().

    Why a helper: Python 3.12 deprecates datetime.utcnow() (returns naive datetime).
    Centering the fix here means we change ~20 call sites by editing one line,
    and any future deprecation (e.g. Python 3.16) needs updating only here.
    """
    return datetime.now(timezone.utc)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False

def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    import uuid  # v1.5-A: JWT blacklist butuh JTI unik per token
    to_encode = data.copy()
    # python-jose: 'sub' claim WAJIB string, bukan int.
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": "FLIPUS-UKIKT",
        "watermark": "FLIPUS_v1.1",
        "jti": uuid.uuid4().hex,  # v1.5-A: unique token ID untuk blacklist
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode JWT — support dual-key rotation (T51).

    Flow:
    1. Try decode dengan SECRET_KEY (primary)
    2. Kalau gagal DAN SECRET_KEY_PREVIOUS di-set → try decode dengan previous
    3. Kalau masih gagal → return None

    Ini memungkinkan graceful rotation: setelah SECRET_KEY di-rotate, JWT lama
    masih valid selama grace window (default 24 jam), supaya user tidak ter-logout
    mendadak saat rotasi.

    Catatan: untuk sign (encode), selalu pakai SECRET_KEY primary. JWT baru
    akan menggunakan key baru; JWT lama valid via fallback ke previous.
    """
    # Primary key
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_iat": False, "verify_aud": False},
        )
    except JWTError:
        pass

    # Fallback ke previous key (T51 rotation grace window)
    if settings.SECRET_KEY_PREVIOUS:
        try:
            return jwt.decode(
                token,
                settings.SECRET_KEY_PREVIOUS,
                algorithms=[settings.ALGORITHM],
                options={"verify_iat": False, "verify_aud": False},
            )
        except JWTError:
            pass

    return None

def encrypt_pii(plain_text: str) -> str:
    return fernet.encrypt(plain_text.encode()).decode()

def decrypt_pii(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return ""

def generate_tenant_signature(uni: str, kantor_misi: str, jemaat: str) -> str:
    raw = f"{uni}|{kantor_misi}|{jemaat}|{settings.LICENSE_TENANT_SIGNATURE_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


def require_admin_bootstrap_dependency(
    request: Request,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    """
    FastAPI dependency: header `X-Admin-Token` harus cocok dengan
    `settings.ADMIN_BOOTSTRAP_TOKEN`.

    Audit: setiap attempt (success atau failure) di-log dengan IP address.
    Set `ADMIN_BOOTSTRAP_TOKEN` di .env sebelum pakai. Generate dengan:
        python3 -c "import secrets; print(secrets.token_hex(32))"
    """
    from app.core.database import SessionLocal
    from app.models.audit import AuditLog

    expected = settings.ADMIN_BOOTSTRAP_TOKEN or ""
    if not expected:
        raise HTTPException(
            status_code=_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_BOOTSTRAP_TOKEN belum di-set di .env. Endpoint ini disable sampai Jerry set token.",
        )

    client_ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "unknown")[:200]

    if not x_admin_token or x_admin_token != expected:
        # Audit failure attempt
        try:
            db = SessionLocal()
            db.add(AuditLog(
                tenant_id=0,  # 0 = global, no tenant scope
                action=f"ADMIN_BOOTSTRAP_DENIED_ip_{client_ip}",
                payload_hash=(x_admin_token or "")[:32],
            ))
            db.commit()
            db.close()
        except Exception:
            pass
        raise HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-Token tidak valid atau tidak diberikan",
        )

    # Success audit
    try:
        db = SessionLocal()
        db.add(AuditLog(
            tenant_id=0,
            action=f"ADMIN_BOOTSTRAP_OK_ip_{client_ip}_ua_{ua[:80]}",
            payload_hash=client_ip,
        ))
        db.commit()
        db.close()
    except Exception:
        pass

    return True
