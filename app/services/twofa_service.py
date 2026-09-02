"""
FLIPUS v1.3 — TOTP 2FA Service (Tahap 23).

Standard RFC 6238 TOTP (Time-based One-Time Password).
Compatible dengan Google Authenticator, Authy, 1Password, dll.

Usage:
    secret = generate_secret()
    uri = get_provisioning_uri(secret, "username", "FLIPUS")
    qrcode = generate_qr_code_base64(uri)
    is_valid = verify_totp(secret, "123456")
    codes = generate_backup_codes()
"""

import base64
import io
import secrets
import string
from typing import List, Tuple

import pyotp
import qrcode

from app.core.security import encrypt_pii, decrypt_pii, hash_password


# ===== Constants =====
ISSUER_NAME = "FLIPUS GMAHK UKIKT"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 10
TOTP_VALID_WINDOW = 1  # accept code from ±1 step (30s each = 90s window)


# ===== Secret Generation =====

def generate_secret() -> str:
    """Generate a random base32-encoded TOTP secret (160 bits)."""
    return pyotp.random_base32(length=32)


# ===== QR Code =====

def get_provisioning_uri(secret: str, username: str, issuer: str = ISSUER_NAME) -> str:
    """Build otpauth:// URI for QR code (standard)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=issuer,
    )


def generate_qr_code_base64(uri: str) -> str:
    """Generate QR code as base64 PNG (data URI ready).

    Returns: 'data:image/png;base64,...'
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    buf.close()
    return f"data:image/png;base64,{b64}"


# ===== TOTP Verification =====

def verify_totp(secret: str, code: str, valid_window: int = TOTP_VALID_WINDOW) -> bool:
    """Verify a 6-digit TOTP code against the secret.

    valid_window: how many steps (30s each) before/after to accept
    - 0 = exact 30s slot
    - 1 = +/- 30s (90s total window) — RECOMMENDED
    """
    if not secret or not code:
        return False
    # Strip whitespace and normalize
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=valid_window)


# ===== Backup Codes =====

def generate_backup_codes(count: int = BACKUP_CODE_COUNT, length: int = BACKUP_CODE_LENGTH) -> List[str]:
    """Generate single-use backup codes (readable format).

    Format: ABC12-DEF34 (uppercase + digits, dash in middle)
    """
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(length))
        # Insert dash at midpoint for readability
        code = f"{raw[:length//2]}-{raw[length//2:]}"
        codes.append(code)
    return codes


def hash_backup_codes(codes: List[str]) -> List[str]:
    """Hash each backup code with bcrypt for secure storage."""
    return [hash_password(code) for code in codes]


def verify_backup_code(code: str, hashed_list: List[str]) -> Tuple[bool, int]:
    """Verify a backup code against the hashed list.

    Returns:
        (is_valid, index_of_match) where index_of_match is the position in the list.
        If valid, caller should remove that index from the list (single-use).
    """
    if not code or not hashed_list:
        return False, -1
    from app.core.security import verify_password
    for i, hashed in enumerate(hashed_list):
        if verify_password(code, hashed):
            return True, i
    return False, -1


# ===== Secret Encryption Helpers =====

def encrypt_secret(secret: str) -> str:
    """Encrypt TOTP secret sebelum disimpan di DB."""
    return encrypt_pii(secret)


def decrypt_secret(encrypted: str) -> str:
    """Decrypt TOTP secret setelah di-load dari DB."""
    return decrypt_pii(encrypted)


# ===== Setup Wizard Helpers =====

def build_setup_response(user, secret: str) -> dict:
    """Build response untuk /2fa/setup endpoint.

    Returns:
        {
            "secret": "...",  # plain (user should keep this offline)
            "qr_code": "data:image/png;base64,...",  # untuk QR scanner
            "otpauth_url": "otpauth://...",  # untuk manual entry
            "issuer": "FLIPUS",
            "username": "...",
        }
    """
    uri = get_provisioning_uri(secret, user.username, ISSUER_NAME)
    qr_base64 = generate_qr_code_base64(uri)
    return {
        "secret": secret,
        "qr_code": qr_base64,
        "otpauth_url": uri,
        "issuer": ISSUER_NAME,
        "username": user.username,
    }
