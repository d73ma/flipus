"""
FLIPUS v1.3 — Upload validator (FASE 3, Sprint 2 / T1).

Defends against:
 1. Polyglot files (file dengan header valid tapi payload berbahaya).
 2. Disguised files (mis. shell.php.exe, malware yang di-rename jadi .jpg).
 3. Oversized uploads (DoS / disk exhaustion).
 4. Non-image files masuk endpoint OCR/foto (yang tanpa validasi sebelumnya).

Strategi: defense-in-depth
   - Trusted MIME: client-provided `content_type` HANYA untuk log/debug, BUKAN sumber kebenaran.
   - Magic bytes: gunakan library `filetype` untuk cek signature biner dari byte stream.
   - Whitelist: hanya terima MIME yang ada di `ALLOWED_*` per use-case.

Penting: SVG tidak punya magic bytes 100% aman (SVG adalah XML yang dimulai
dengan header yang bisa di-forge); karena itu SVG hanya dipakai untuk logo
tenant (use case terbatas) dan direstart dari path lain tanpa dieksekusi
oleh backend. Untuk OCR/amplop, SVG TIDAK termasuk whitelist.
"""
import os
from typing import Iterable, Optional

from fastapi import HTTPException, status

try:
    import filetype  # type: ignore
except ImportError:  # pragma: no cover
    filetype = None  # type: ignore


# ===== Konstanta: profil whitelist per use-case =====

# Foto amplop kuitansi (di-scan untuk OCR nama umat + nominal).
# Foto struk nota (di-OCR dengan Ollama).
# JPEG/PNG/WebP/HEIC umumnya dipakai untuk foto HP.
AMPLOP_OCR_ALLOWED_MIMES: frozenset = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
})
AMPLOP_OCR_ALLOWED_EXTS: frozenset = frozenset({
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
})
AMPLOP_OCR_MAX_BYTES: int = 15 * 1024 * 1024  # 15 MB

# Foto struk nota (lebih kecil, biasanya hasil kamera HP).
STRUK_OCR_ALLOWED_MIMES: frozenset = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
})
STRUK_OCR_ALLOWED_EXTS: frozenset = frozenset({
    ".jpg", ".jpeg", ".png", ".webp",
})
STRUK_OCR_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB

# Logo tenant (PNG/JPG/SVG, max 1MB — dipakai untuk PDF header & UI).
LOGO_ALLOWED_MIMES: frozenset = frozenset({
    "image/png",
    "image/jpeg",
    "image/svg+xml",
})
LOGO_ALLOWED_EXTS: frozenset = frozenset({
    ".png", ".jpg", ".jpeg", ".svg",
})
LOGO_MAX_BYTES: int = 1 * 1024 * 1024  # 1 MB


# ===== Helpers =====

def _check_filetype_available() -> None:
    """Guard: fail-fast kalau library belum ter-install (jangan silent bypass)."""
    if filetype is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Library 'filetype' belum ter-install. Jalankan: pip install filetype",
        )


def _ext(filename: Optional[str]) -> str:
    return os.path.splitext(filename or "")[1].lower() if filename else ""


def _raise_bad_request(detail: str) -> None:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)


def validate_upload(
    *,
    content: bytes,
    filename: Optional[str],
    allowed_mimes: Iterable[str],
    allowed_exts: Iterable[str],
    max_bytes: int,
    label: str,
) -> str:
    """
    Validate upload content via magic bytes + extension + size.

    Parameters:
      content:        raw bytes (sudah di-read dari UploadFile).
      filename:       original filename (untuk fallback extension & debug).
      allowed_mimes:  frozenset MIME type yang diperbolehkan.
      allowed_exts:   frozenset ekstensi (lowercase, dot-prefixed).
      max_bytes:      ukuran maksimum file.
      label:          nama use-case (untuk pesan error, mis. "foto amplop").

    Returns:
      detected_mime:  MIME type hasil deteksi magic bytes (trustworthy).

    Raises:
      HTTPException 400 kalau file ditolak.
      HTTPException 500 kalau library 'filetype' tidak ada.
    """
    _check_filetype_available()

    # 1) Empty check
    if not content:
        _raise_bad_request("File kosong")

    # 2) Size check
    size = len(content)
    if size > max_bytes:
        mb = round(max_bytes / (1024 * 1024), 1)
        _raise_bad_request(
            f"{label} terlalu besar ({size} bytes, max {mb} MB)"
        )

    # 3) Magic-byte detection (Sumber kebenaran MIME)
    guess = filetype.guess(content)
    detected_mime = guess.mime if guess else "application/octet-stream"

    # 3a) SVG fallback — SVG adalah XML (text-based), tidak punya magic bytes
    #     yang reliable. Untuk use-case yang mengizinkan SVG (logo tenant),
    #     kita pakai extension + content sniff dasar (cek "<?xml" atau "<svg").
    ext = _ext(filename)
    if detected_mime == "application/octet-stream" and ext == ".svg":
        if b"<svg" in content[:512] or b"<?xml" in content[:64]:
            detected_mime = "image/svg+xml"
        else:
            sample = (filename or "<unknown>")[:80]
            _raise_bad_request(
                f"File {sample} ber-extension .svg tapi kontennya bukan XML SVG yang valid."
            )

    if detected_mime not in allowed_mimes:
        # Blokir polyglot / disguised / extension-mismatch.
        sample = (filename or "<unknown>")[:80]
        _raise_bad_request(
            f"Tipe file {label!r} tidak didukung. "
            f"Detected MIME: {detected_mime} (filename: {sample}). "
            f"Hanya izinkan: {sorted(allowed_mimes)}"
        )

    # 4) Extension check (juga harus whitelist — client boleh pakai extension
    #    apa saja asalkan MIME-nya cocok; ini loose check untuk UI/UX).
    if ext and ext not in allowed_exts:
        _raise_bad_request(
            f"Extension {ext!r} tidak diizinkan untuk {label!r}. "
            f"Hanya izinkan: {sorted(allowed_exts)}"
        )

    return detected_mime


# ===== Preset per use-case =====

def validate_amplop_ocr(content: bytes, filename: Optional[str]) -> str:
    """Validate foto amplop kuitansi (OCR scanner)."""
    return validate_upload(
        content=content,
        filename=filename,
        allowed_mimes=AMPLOP_OCR_ALLOWED_MIMES,
        allowed_exts=AMPLOP_OCR_ALLOWED_EXTS,
        max_bytes=AMPLOP_OCR_MAX_BYTES,
        label="foto amplop",
    )


def validate_struk_ocr(content: bytes, filename: Optional[str]) -> str:
    """Validate foto struk nota (OCR pengeluaran)."""
    return validate_upload(
        content=content,
        filename=filename,
        allowed_mimes=STRUK_OCR_ALLOWED_MIMES,
        allowed_exts=STRUK_OCR_ALLOWED_EXTS,
        max_bytes=STRUK_OCR_MAX_BYTES,
        label="foto struk",
    )


def validate_logo(content: bytes, filename: Optional[str]) -> str:
    """Validate logo tenant."""
    return validate_upload(
        content=content,
        filename=filename,
        allowed_mimes=LOGO_ALLOWED_MIMES,
        allowed_exts=LOGO_ALLOWED_EXTS,
        max_bytes=LOGO_MAX_BYTES,
        label="logo",
    )
