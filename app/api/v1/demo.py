"""
FLIPUS v1.3 — Demo mode (public, no auth) untuk quick demo.

Endpoint:
- GET /v1/demo/login-as/{role}?tenant_slug=... → auto-create JWT token untuk user demo
- Role tersedia: bendahara, ketua, pendeta, auditor, admin
- Optional ?tenant_slug= untuk pilih jemaat spesifik (nataan-ratahan / sentrum-minahasa)

Demo token:
- Expire 30 menit
- Flag is_demo=True di payload (untuk banner warning di frontend)
- Auto-pick user demo pertama untuk role tsb (filter by tenant_slug kalau ada)
- Disable destructive actions via check_dependencies

Untuk production: disable endpoint ini via env var DEMO_MODE_ENABLED=false
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter()


class DemoLoginOut(BaseModel):
    access_token: str
    role: str
    tenant_id: int
    tenant_slug: str | None = None
    redirect_to: str
    is_demo: bool = True
    expires_in_minutes: int = 30


# Mapping role → (username_pattern, dashboard_path)
DEMO_USERS = {
    "bendahara": ("bendahara_a", "/bendahara"),
    "ketua": ("ketua_a", "/ketua"),
    "pendeta": ("pendeta_a", "/pendeta"),
    "auditor": ("auditor_misi", "/auditor"),
    "admin": ("admin_uni", "/admin"),
}


def _is_demo_enabled() -> bool:
    """Demo mode default ON untuk development. Set DEMO_MODE_ENABLED=false di production."""
    return os.getenv("DEMO_MODE_ENABLED", "true").lower() == "true"


@router.get("/login-as/{role}", tags=['Demo'], response_model=DemoLoginOut)
def demo_login_as(
    role: str,
    tenant_slug: str | None = Query(
        None,
        description="Pilih jemaat via slug (mis. nataan-ratahan, sentrum-minahasa). "
                    "Kalau kosong, pakai jemaat default (Nataan).",
    ),
    db: Session = Depends(get_db),
):
    """
    Auto-login sebagai user demo untuk role tertentu.

    Public endpoint (no auth) — cocok untuk calon jemaat/admin yang mau
    lihat-lihat dashboard tanpa perlu register dulu.

    Query params:
        tenant_slug: pilih jemaat spesifik (untuk multi-tenant demo).
                     Contoh: ?tenant_slug=sentrum-minahasa

    Returns:
        access_token: JWT 30 menit
        role: role user demo
        tenant_id: tenant id
        tenant_slug: tenant slug untuk multi-tenant routing
        redirect_to: path dashboard sesuai role
        is_demo: True (frontend pakai ini untuk banner warning)
    """
    if not _is_demo_enabled():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Mode demo disabled di production. Set DEMO_MODE_ENABLED=true di .env untuk enable.",
        )

    role_lower = role.lower().strip()
    if role_lower not in DEMO_USERS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Role demo '{role}' tidak dikenal. Pilihan: {list(DEMO_USERS.keys())}",
        )

    username, redirect_to = DEMO_USERS[role_lower]

    # Filter by tenant_slug kalau ada
    user_query = (
        db.query(User)
        .filter(User.username == username, User.is_active == True)  # noqa: E712
    )
    target_tenant = None
    if tenant_slug:
        target_tenant = (
            db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        )
        if not target_tenant:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Jemaat dengan slug '{tenant_slug}' tidak ditemukan.",
            )
        user_query = user_query.filter(User.tenant_id == target_tenant.id)
    user = user_query.first()
    if not user:
        # Fallback: kalau tidak ada user dengan username itu untuk tenant tsb (mis. admin_uni),
        # pakai user pertama dengan role tsb di tenant tsb.
        if target_tenant:
            role_upper = {
                "bendahara": "BENDAHARA",
                "ketua": "KETUA_KEUANGAN",
                "pendeta": "PENDETA",
                "auditor": "AUDITOR_MISI",
                "admin": "ADMIN_UNI",
            }.get(role_lower, role_lower.upper())
            user = (
                db.query(User)
                .filter(
                    User.tenant_id == target_tenant.id,
                    User.role == role_upper,
                    User.is_active == True,  # noqa: E712
                )
                .first()
            )
        if not user:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"User demo '{username}' belum ada untuk jemaat ini. Jalankan seed_demo.py dulu.",
            )

    # Get tenant slug
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    tenant_slug_out = tenant.slug if tenant else None

    # Create JWT token 30 menit dengan flag is_demo
    token_payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_slug": tenant_slug_out,
        "is_demo": True,
        "username": user.username,
    }
    access_token = create_access_token(token_payload, expires_minutes=30)

    return DemoLoginOut(
        access_token=access_token,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=tenant_slug_out,
        redirect_to=redirect_to,
        is_demo=True,
        expires_in_minutes=30,
    )


@router.get("/info", tags=['Demo'])
def demo_info():
    """Info mode demo (untuk landing page banner)."""
    return {
        "enabled": _is_demo_enabled(),
        "available_roles": list(DEMO_USERS.keys()),
        "session_minutes": 30,
        "warning": "Mode demo: data dummy, button destruktif disabled, auto-logout 30 menit.",
    }


class TenantBrandingPreview(BaseModel):
    """Public info jemaat untuk landing page (no PII)."""
    slug: str
    nama_jemaat: str
    nama_uni: str
    initial: str
    primary_color: str
    secondary_color: str
    logo_url: str | None
    footer_text: str | None = None
    demo_user_count: int  # berapa user demo di jemaat ini


@router.get("/tenants", tags=['Demo'], response_model=list[TenantBrandingPreview])
def demo_list_tenants(db: Session = Depends(get_db)):
    """
    List jemaat dengan branding preview (untuk landing page).

    Public endpoint, no PII — hanya info branding (nama, warna, logo).
    Digunakan landing page untuk showcase jemaat + multi-tenant.
    """
    from app.models.tenant import Tenant
    tenants = (
        db.query(Tenant)
        .filter(Tenant.status == "active")
        .order_by(Tenant.id)
        .all()
    )
    out: list[TenantBrandingPreview] = []
    for t in tenants:
        demo_user_count = (
            db.query(User)
            .filter(User.tenant_id == t.id, User.is_active == True)  # noqa: E712
            .count()
        )
        out.append(TenantBrandingPreview(
            slug=t.slug or "",
            nama_jemaat=t.nama_jemaat_lokal,
            nama_uni=t.nama_uni,
            initial=t.initial_jemaat or t.nama_jemaat_lokal[:2].upper(),
            primary_color=t.primary_color or "#1B4332",
            secondary_color=t.secondary_color or "#F5EFE0",
            logo_url=t.logo_url,
            footer_text=t.footer_text,
            demo_user_count=demo_user_count,
        ))
    return out
