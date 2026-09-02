"""
FLIPUS v1.3 — Branding service (Tahap 21).

Helper untuk upload logo, validate colors, manage branding metadata.
Logo disimpan di /storage/tenants/{tenant_id}/logo.{ext}
"""

import os
import re
import uuid
from datetime import datetime
from app.core.security import utcnow
from typing import Optional, Tuple
from pathlib import Path

from sqlalchemy.orm import Session
from PIL import Image

from app.models.tenant import Tenant
from app.models.audit import AuditLog


# ===== Constants =====
STORAGE_ROOT = Path("storage")
TENANT_LOGO_DIR = STORAGE_ROOT / "tenants"

ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}
ALLOWED_LOGO_MIME_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/svg+xml",
}
MAX_LOGO_SIZE_BYTES = 1 * 1024 * 1024  # 1 MB
MAX_LOGO_DIMENSION = 512  # pixels (auto-resize jika lebih besar)


# ===== Helpers =====

def _validate_hex_color(color: str) -> str:
    """
    Validate hex color format (#RRGGBB atau #RGB).
    Returns normalized '#RRGGBB' (lowercase).
    Raises ValueError kalau invalid.
    """
    if not color:
        raise ValueError("Color kosong")
    c = color.strip()
    if not re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", c):
        raise ValueError(f"Format color '{color}' tidak valid (gunakan #RRGGBB)")
    # Normalize #RGB → #RRGGBB
    if len(c) == 4:
        c = "#" + c[1] * 2 + c[2] * 2 + c[3] * 2
    return c.lower()


def _validate_logo_file(filename: str, content_type: str, size: int) -> str:
    """Validate logo file. Return extension. Raises ValueError kalau invalid."""
    if size > MAX_LOGO_SIZE_BYTES:
        raise ValueError(f"Logo terlalu besar ({size} bytes, max {MAX_LOGO_SIZE_BYTES})")
    if content_type not in ALLOWED_LOGO_MIME_TYPES:
        raise ValueError(f"Tipe file '{content_type}' tidak didukung (PNG/JPG/SVG)")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise ValueError(f"Extension '{ext}' tidak didukung (PNG/JPG/SVG)")
    return ext


def _resize_logo_if_needed(input_path: Path, output_path: Path) -> Tuple[int, int]:
    """
    Resize logo jika dimensi > MAX_LOGO_DIMENSION.
    Untuk SVG, skip resize (vector).
    Returns (width, height).
    """
    if input_path.suffix.lower() == ".svg":
        return (-1, -1)  # SVG: dimensi tidak relevan

    try:
        img = Image.open(input_path)
        orig_w, orig_h = img.size
        if orig_w > MAX_LOGO_DIMENSION or orig_h > MAX_LOGO_DIMENSION:
            # Resize maintaining aspect ratio
            img.thumbnail((MAX_LOGO_DIMENSION, MAX_LOGO_DIMENSION), Image.Resampling.LANCZOS)
            img.save(output_path, optimize=True)
        else:
            # Copy as-is
            img.save(output_path, optimize=True)
        return img.size
    except Exception as e:
        raise ValueError(f"Gagal proses gambar: {e}")


def upload_logo(
    db: Session,
    tenant: Tenant,
    file_content: bytes,
    filename: str,
    content_type: str,
    actor_user_id: int,
) -> Tenant:
    """
    Upload logo untuk tenant. Stored at /storage/tenants/{tenant_id}/logo.{ext}.

    Validates:
    - File size <= 1MB
    - MIME type PNG/JPG/SVG
    - Extension valid
    - Image integrity (via PIL)
    - Auto-resize jika dimensi > 512px

    Returns tenant (logo_url sudah diset).
    """
    size = len(file_content)
    ext = _validate_logo_file(filename, content_type, size)

    # Create tenant dir
    tenant_dir = TENANT_LOGO_DIR / str(tenant.id)
    tenant_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename (avoid cache issues)
    unique_name = f"logo_{uuid.uuid4().hex[:8]}{ext}"
    final_path = tenant_dir / unique_name

    # Write temp untuk validate/proses
    temp_path = tenant_dir / f"temp_{uuid.uuid4().hex[:8]}{ext}"
    temp_path.write_bytes(file_content)

    try:
        # Validate + resize
        if ext != ".svg":
            _resize_logo_if_needed(temp_path, final_path)
            temp_path.unlink(missing_ok=True)
        else:
            # SVG: just rename
            temp_path.rename(final_path)

        # Hapus logo lama kalau ada
        if tenant.logo_url:
            old_path = STORAGE_ROOT / tenant.logo_url.lstrip("/")
            if old_path.exists() and old_path != final_path:
                old_path.unlink(missing_ok=True)

        # Update tenant
        tenant.logo_url = f"tenants/{tenant.id}/{unique_name}"
        tenant.branding_updated_at = utcnow()
        tenant.branding_updated_by = actor_user_id

        db.add(AuditLog(
            tenant_id=tenant.id,
            action=f"BRANDING_LOGO_UPLOADED_by_user_{actor_user_id}",
            payload_hash=filename,
        ))
        db.flush()
        return tenant
    except Exception:
        # Cleanup kalau gagal
        temp_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def update_branding(
    db: Session,
    tenant: Tenant,
    primary_color: Optional[str] = None,
    secondary_color: Optional[str] = None,
    footer_text: Optional[str] = None,
    actor_user_id: int = 0,
) -> Tenant:
    """
    Update branding metadata (color + footer text).
    Validates hex color format jika diberikan.
    """
    if primary_color is not None:
        tenant.primary_color = _validate_hex_color(primary_color)
    if secondary_color is not None:
        tenant.secondary_color = _validate_hex_color(secondary_color)
    if footer_text is not None:
        # Limit 255 chars
        text = footer_text.strip()[:255]
        tenant.footer_text = text or None

    tenant.branding_updated_at = utcnow()
    if actor_user_id:
        tenant.branding_updated_by = actor_user_id

    db.add(AuditLog(
        tenant_id=tenant.id,
        action=f"BRANDING_UPDATED_by_user_{actor_user_id}",
        payload_hash=f"primary={tenant.primary_color},secondary={tenant.secondary_color}",
    ))
    db.flush()
    return tenant


def get_logo_path(tenant: Tenant) -> Optional[Path]:
    """Return absolute path to tenant logo, or None."""
    if not tenant.logo_url:
        return None
    # Normalize: logo_url is relative "/tenants/{id}/logo.png"
    rel = tenant.logo_url.lstrip("/")
    path = STORAGE_ROOT / rel
    return path if path.exists() else None


def get_tenant_branding_dict(tenant: Tenant) -> dict:
    """Return branding dict untuk API response."""
    return {
        "logo_url": tenant.logo_url,
        "primary_color": tenant.primary_color,
        "secondary_color": tenant.secondary_color,
        "footer_text": tenant.footer_text,
        "branding_updated_at": str(tenant.branding_updated_at) if tenant.branding_updated_at else None,
        "branding_updated_by": tenant.branding_updated_by,
    }
