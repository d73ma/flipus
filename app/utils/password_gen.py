"""
FLIPUS v1.4 — Random password generator untuk user baru & reset password.

Karakter yang dipakai: uppercase + lowercase + digits, KECUALI ambiguous chars
(0/O, 1/l/I) untuk hindari salah baca di WA message.

T49 hardening: panjang minimal 8 karakter (sebelumnya 6). Validasi entropy:
minimal 1 upper, 1 lower, 1 digit.
"""

import secrets
import string

# Exclude ambiguous chars
_EXCLUDE = set("0O1lI")
_CHARSET = "".join(c for c in (string.ascii_letters + string.digits) if c not in _EXCLUDE)


# T49: Password policy constants
MIN_PASSWORD_LENGTH = 8  # Jerry's policy: minimal 8 karakter
MAX_PASSWORD_LENGTH = 64


def generate_random_password(length: int = MIN_PASSWORD_LENGTH) -> str:
    """
    Generate random password dengan entropy tinggi.

    Args:
        length: panjang password (default 8, MIN_PASSWORD_LENGTH untuk policy compliance)

    Returns:
        String random dengan minimal 1 upper, 1 lower, 1 digit.

    Raises:
        ValueError: jika length < MIN_PASSWORD_LENGTH atau length > MAX_PASSWORD_LENGTH.

    T49: Semua password yang di-generate oleh sistem harus comply dengan policy:
    - Minimal 8 karakter
    - Mengandung minimal 1 huruf besar, 1 huruf kecil, 1 angka
    """
    if length < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"length minimal {MIN_PASSWORD_LENGTH} (T49 policy), dapat: {length}"
        )
    if length > MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"length maksimal {MAX_PASSWORD_LENGTH}, dapat: {length}"
        )
    if length > len(_CHARSET):
        raise ValueError("length terlalu panjang untuk charset yang tersedia")

    # Pakai secrets.choice untuk crypto-safe random
    while True:
        pwd = "".join(secrets.choice(_CHARSET) for _ in range(length))
        # Validasi entropy: minimal 1 upper, 1 lower, 1 digit
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    T49: Validasi password memenuhi policy.

    Untuk password yang di-input manual (future feature).
    Returns (is_valid, error_message).

    Policy:
    - Minimal 8 karakter
    - Mengandung minimal 1 huruf besar (A-Z)
    - Mengandung minimal 1 huruf kecil (a-z)
    - Mengandung minimal 1 angka (0-9)
    """
    if not password:
        return False, "Password tidak boleh kosong"
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password minimal {MIN_PASSWORD_LENGTH} karakter (saat ini: {len(password)})"
    if len(password) > MAX_PASSWORD_LENGTH:
        return False, f"Password maksimal {MAX_PASSWORD_LENGTH} karakter"
    if not any(c.isupper() for c in password):
        return False, "Password harus mengandung minimal 1 huruf besar (A-Z)"
    if not any(c.islower() for c in password):
        return False, "Password harus mengandung minimal 1 huruf kecil (a-z)"
    if not any(c.isdigit() for c in password):
        return False, "Password harus mengandung minimal 1 angka (0-9)"
    return True, ""


def mask_password(password: str, visible: int = 2) -> str:
    """
    Mask password untuk display (misal log audit): 'Se****23'.

    Args:
        password: password asli
        visible: jumlah char visible di awal dan akhir

    Returns:
        String masked, misal 'Se****23' dari 'Secret23'.
    """
    if not password or len(password) <= visible * 2:
        return "*" * len(password) if password else ""
    return (
        password[:visible]
        + "*" * (len(password) - visible * 2)
        + password[-visible:]
    )
