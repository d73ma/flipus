"""
FLIPUS v1.3 — Tenant service.

Helper untuk resolve tenant by slug/subdomain/id, dan auto-generate
slug unik dari nama_jemaat_lokal.

Slug rules:
- Lowercase, alphanumeric + dash
- Max 80 chars
- Trim leading/trailing dashes
- Collision suffix: -2, -3, ... (max sampai -999)
- Reserved: 'admin', 'api', 'www', 'app', 'static', 'docs', 'auth',
  'register', 'login', 'logout', 'dashboard', 'health', 'system',
  'master', 'backup', 'audit', 'tenant', 'tenants'
"""

import re
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.tenant import Tenant
from app.core.security import generate_tenant_signature


# Reserved slugs (tidak boleh dipakai tenant karena bentrok dgn path API)
RESERVED_SLUGS = {
    "admin", "api", "www", "app", "static", "docs", "auth", "register",
    "login", "logout", "dashboard", "health", "system", "master", "backup",
    "audit", "tenant", "tenants", "root", "support", "help",
}


def slugify(name: str, max_len: int = 60) -> str:
    """
    Convert nama_jemaat_lokal ke URL-safe slug.

    Contoh:
        "Jemaat Nataan Ratahan"     → "jemaat-nataan-ratahan"
        "GMAHK Kec. Tombatu"       → "gmahk-kec-tombatu"
        "Stadion 123!"             → "stadion-123"
    """
    if not name:
        return "tenant"

    # Lowercase
    s = name.lower().strip()

    # Replace non-alphanumeric dengan dash
    s = re.sub(r"[^a-z0-9]+", "-", s)

    # Collapse multiple dashes
    s = re.sub(r"-+", "-", s)

    # Trim leading/trailing dashes
    s = s.strip("-")

    # Truncate
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")

    # Fallback kalau kosong setelah slugify
    if not s:
        return "tenant"

    # Reserved check
    if s in RESERVED_SLUGS:
        s = f"{s}-jemaat"

    return s


def generate_unique_slug(db: Session, nama_jemaat: str, exclude_tenant_id: Optional[int] = None) -> str:
    """
    Generate slug unique dari nama_jemaat.

    Jika slug sudah ada, suffix -2, -3, dst sampai ketemu yang free.
    Skip collisions yang jadi tenant_id == exclude_tenant_id (untuk update case).
    """
    base = slugify(nama_jemaat)
    candidate = base

    for i in range(1, 1000):
        existing = (
            db.query(Tenant)
            .filter(Tenant.slug == candidate)
            .first()
        )
        if not existing:
            return candidate
        if exclude_tenant_id is not None and existing.id == exclude_tenant_id:
            return candidate
        candidate = f"{base}-{i + 1}"

    # Hard fallback (shouldn't happen)
    return f"{base}-{abs(hash(nama_jemaat)) % 100000}"


def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    """Lookup tenant by slug (exact match)."""
    return db.query(Tenant).filter(Tenant.slug == slug.strip().lower()).first()


def get_tenant_by_subdomain(db: Session, subdomain: str) -> Optional[Tenant]:
    """Lookup tenant by subdomain (exact match)."""
    return db.query(Tenant).filter(Tenant.subdomain == subdomain.strip().lower()).first()


def get_tenant_by_slug_or_subdomain(db: Session, identifier: str) -> Optional[Tenant]:
    """Lookup by slug OR subdomain in one query."""
    ident = identifier.strip().lower()
    return (
        db.query(Tenant)
        .filter(or_(Tenant.slug == ident, Tenant.subdomain == ident))
        .first()
    )


def ensure_slug(db: Session, tenant: Tenant) -> Tenant:
    """
    Ensure tenant punya slug. Backfill kalau legacy tenant belum punya.
    Return tenant (sama) untuk chaining.
    """
    if not tenant.slug:
        tenant.slug = generate_unique_slug(db, tenant.nama_jemaat_lokal, exclude_tenant_id=tenant.id)
        db.flush()
    return tenant


def register_tenant(
    db: Session,
    nama_uni: str,
    nama_kantor_misi: str,
    nama_jemaat_lokal: str,
    nama_pendeta: str = "",
    nama_ketua_keuangan: str = "",
    nama_bendahara: str = "",
) -> Tenant:
    """
    Legacy onboarding endpoint helper (Tahap 15 era).
    Create tenant baru + auto-generate slug + tenant_signature.

    Returns the created Tenant instance.
    """
    t = Tenant(
        tenant_signature=generate_tenant_signature(nama_uni, nama_kantor_misi, nama_jemaat_lokal),
        nama_uni=nama_uni,
        nama_kantor_misi=nama_kantor_misi,
        nama_jemaat_lokal=nama_jemaat_lokal,
        nama_pendeta=nama_pendeta or None,
        nama_ketua_keuangan=nama_ketua_keuangan or None,
        nama_bendahara=nama_bendahara or None,
        status="active",
        is_active=True,
        plan="free",
    )
    db.add(t)
    db.flush()  # need t.id for slug uniqueness check
    t.slug = generate_unique_slug(db, nama_jemaat_lokal, exclude_tenant_id=t.id)
    db.commit()
    db.refresh(t)
    return t
