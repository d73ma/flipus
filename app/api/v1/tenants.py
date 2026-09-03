"""
FLIPUS v1.3 — Tenant administration endpoints (Tahap 20 + 21).

GET    /api/v1/tenants/resolve/{slug-or-subdomain}  — public lookup (info-only)
GET    /api/v1/tenants/me                            — current tenant info (any role)
GET    /api/v1/tenants/                              — list tenants (admin uni only)
GET    /api/v1/tenants/{tenant_id}                   — tenant detail (admin uni only)
PATCH  /api/v1/tenants/{tenant_id}                   — update tenant profile (admin uni only)
PATCH  /api/v1/tenants/{tenant_id}/status            — change status (admin uni only)
PATCH  /api/v1/tenants/{tenant_id}/plan              — change plan (admin uni only)
POST   /api/v1/tenants/{tenant_id}/logo              — upload logo (Tahap 21)
DELETE /api/v1/tenants/{tenant_id}/logo              — remove logo (Tahap 21)
PATCH  /api/v1/tenants/{tenant_id}/branding          — update color + footer (Tahap 21)
GET    /api/v1/tenants/{tenant_id}/branding          — get branding (any role)

RBAC:
- ADMIN_UNI: full access di uni mereka
- AUDITOR_MISI: read-only access di misi mereka
- Others: 403 (kecuali /me dan /resolve)
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.models.master import MisiKonferens, Uni
from app.models.audit import AuditLog
from app.services.tenant_service import (
    slugify,
    generate_unique_slug,
    get_tenant_by_slug,
    get_tenant_by_slug_or_subdomain,
)
from app.services.branding_service import (
    upload_logo,
    update_branding,
    get_logo_path,
    get_tenant_branding_dict,
    _validate_hex_color,
    STORAGE_ROOT,
)
from app.core.upload_validator import validate_logo
# FASE 4 Sprint 6-F: pakai TenantScope untuk isolasi data multi-organisasi.
from app.core.tenant_scope import (
    TenantScope, require_tenant_scope,
)

router = APIRouter()


# ===== Schemas =====

class TenantOut(BaseModel):
    id: int
    slug: str
    subdomain: Optional[str]
    nama_uni: str
    nama_kantor_misi: str
    nama_jemaat_lokal: str
    plan: str
    status: str
    is_active: bool
    contact_email: Optional[str]
    contact_phone: Optional[str]
    owner_user_id: Optional[int]
    nama_pendeta: Optional[str]
    nama_ketua_keuangan: Optional[str]
    nama_bendahara: Optional[str]
    initial_jemaat: Optional[str]
    misi_konferens_id: Optional[int] = None
    uni_id: Optional[int] = None
    created_at: Optional[str]
    updated_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class TenantPublicOut(BaseModel):
    """Public-safe info untuk resolve (no PII)."""
    slug: str
    subdomain: Optional[str]
    nama_uni: str
    nama_kantor_misi: str
    nama_jemaat_lokal: str
    status: str
    plan: str


class TenantUpdateIn(BaseModel):
    """Update tenant profile (admin uni only)."""
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    subdomain: Optional[str] = None
    nama_pendeta: Optional[str] = None
    nama_ketua_keuangan: Optional[str] = None
    nama_bendahara: Optional[str] = None


class StatusChangeIn(BaseModel):
    status: str  # active / suspended / archived
    reason: Optional[str] = None


class PlanChangeIn(BaseModel):
    plan: str  # free / standard / premium
    reason: Optional[str] = None


class TenantsListOut(BaseModel):
    tenants: List[TenantOut]
    count: int


# ===== Helpers =====

def _tenant_to_out(t: Tenant, uni_id: Optional[int] = None) -> TenantOut:
    return TenantOut(
        id=t.id,
        slug=t.slug,
        subdomain=t.subdomain,
        nama_uni=t.nama_uni,
        nama_kantor_misi=t.nama_kantor_misi,
        nama_jemaat_lokal=t.nama_jemaat_lokal,
        plan=t.plan,
        status=t.status,
        is_active=t.is_active,
        contact_email=t.contact_email,
        contact_phone=t.contact_phone,
        owner_user_id=t.owner_user_id,
        nama_pendeta=t.nama_pendeta,
        nama_ketua_keuangan=t.nama_ketua_keuangan,
        nama_bendahara=t.nama_bendahara,
        initial_jemaat=t.initial_jemaat,
        misi_konferens_id=t.misi_konferens_id,
        uni_id=uni_id,
        created_at=str(t.created_at) if t.created_at else None,
        updated_at=str(t.updated_at) if t.updated_at else None,
    )


def _tenant_to_public(t: Tenant) -> TenantPublicOut:
    """Public-safe projection (no PII)."""
    return TenantPublicOut(
        slug=t.slug,
        subdomain=t.subdomain,
        nama_uni=t.nama_uni,
        nama_kantor_misi=t.nama_kantor_misi,
        nama_jemaat_lokal=t.nama_jemaat_lokal,
        status=t.status,
        plan=t.plan,
    )


def _caller_uni(db: Session, current: dict) -> Uni:
    """Resolve Uni of caller. ADMIN_UNI only."""
    tenant = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()
    if not tenant or not tenant.nama_uni:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait Uni")
    uni = db.query(Uni).filter(Uni.nama_resmi == tenant.nama_uni).first()
    if not uni:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uni tidak ditemukan")
    return uni


def _audit_admin_change(db: Session, tenant_id: int, actor_id: int, action: str, payload: str) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        action=f"TENANT_ADMIN_{action}_by_user_{actor_id}",
        payload_hash=payload,
    ))


# ===== PUBLIC RESOLVE =====

@router.get("/resolve/{identifier}", tags=['Tenants'], response_model=TenantPublicOut)
def resolve_tenant(identifier: str, db: Session = Depends(get_db)):
    """
    Public tenant lookup by slug or subdomain.
    Returns info-only (no PII, no contact, no admin metadata).
    Digunakan frontend saat login untuk validasi tenant sebelum kirim username.
    """
    t = get_tenant_by_slug_or_subdomain(db, identifier)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Jemaat '{identifier}' tidak ditemukan")
    return _tenant_to_public(t)


# ===== CURRENT USER'S TENANT =====

@router.get("/me", tags=['Tenants'], response_model=TenantOut)
def get_my_tenant(
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Info tenant caller (untuk navbar/dashboard)."""
    t = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant caller tidak ditemukan")
    # Resolve uni_id via MisiKonferens agar frontend bisa langsung query
    # PersentaseConfig scope=UNI tanpa round-trip tambahan.
    uni_id: Optional[int] = None
    if t.misi_konferens_id:
        m = db.query(MisiKonferens).filter(MisiKonferens.id == t.misi_konferens_id).first()
        if m:
            uni_id = m.uni_id
    return _tenant_to_out(t, uni_id=uni_id)


# ===== ADMIN UNI: LIST =====

@router.get("", tags=['Tenants'], response_model=TenantsListOut)
def list_tenants(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """
    List tenants visible to caller.
    ADMIN_UNI: semua jemaat di uni caller.
    AUDITOR_MISI: semua jemaat di misi caller.

    FASE 4 S6-F: gunakan scope.visible_tenant_ids (single source of truth)
    menggantikan inline `nama_uni == caller_uni.nama_resmi` dan
    `misi_konferens_id == caller_tenant.misi_konferens_id`.
    """
    if scope.role not in ("ADMIN_UNI", "AUDITOR_MISI"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Role ini tidak boleh list tenant",
        )

    if not scope.visible_tenant_ids:
        # Caller tidak punya akses ke tenant manapun (e.g. auditor belum terkait misi).
        return TenantsListOut(tenants=[], count=0)

    q = db.query(Tenant).filter(Tenant.id.in_(scope.visible_tenant_ids))

    tenants = q.order_by(Tenant.nama_jemaat_lokal).all()
    return TenantsListOut(
        tenants=[_tenant_to_out(t) for t in tenants],
        count=len(tenants),
    )


# ===== ADMIN UNI: DETAIL =====

@router.get("/{tenant_id}", tags=['Tenants'], response_model=TenantOut)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Get tenant by ID. ADMIN_UNI only."""
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")
    return _tenant_to_out(target)


# ===== ADMIN UNI: UPDATE PROFILE =====

@router.patch("/{tenant_id}", tags=['Tenants'], response_model=TenantOut)
def update_tenant(
    tenant_id: int,
    payload: TenantUpdateIn,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Update tenant profile (contact + pejabat). ADMIN_UNI only."""
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    # Update subdomain kalau diberikan (cek uniqueness)
    if payload.subdomain is not None and payload.subdomain != target.subdomain:
        new_sub = payload.subdomain.strip().lower() or None
        if new_sub:
            # Slugify validasi
            slugified = slugify(new_sub)
            if slugified != new_sub:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Subdomain '{new_sub}' tidak valid (gunakan format: {slugified})",
                )
            existing = (
                db.query(Tenant)
                .filter(Tenant.subdomain == new_sub)
                .filter(Tenant.id != target.id)
                .first()
            )
            if existing:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Subdomain '{new_sub}' sudah dipakai")
            target.subdomain = new_sub

    # Update contact
    if payload.contact_email is not None:
        target.contact_email = payload.contact_email or None
    if payload.contact_phone is not None:
        target.contact_phone = payload.contact_phone or None

    # Update pejabat (Level 2)
    if payload.nama_pendeta is not None:
        target.nama_pendeta = payload.nama_pendeta or None
    if payload.nama_ketua_keuangan is not None:
        target.nama_ketua_keuangan = payload.nama_ketua_keuangan or None
    if payload.nama_bendahara is not None:
        target.nama_bendahara = payload.nama_bendahara or None

    db.flush()
    _audit_admin_change(
        db, target.id, current["id"], "PROFILE_UPDATED",
        f"contact_email={payload.contact_email}, subdomain={payload.subdomain}",
    )
    db.commit()
    db.refresh(target)
    return _tenant_to_out(target)


# ===== ADMIN UNI: STATUS CHANGE =====

@router.patch("/{tenant_id}/status", tags=['Tenants'], response_model=TenantOut)
def change_tenant_status(
    tenant_id: int,
    payload: StatusChangeIn,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Change tenant status (active / suspended / archived). ADMIN_UNI only.

    Efek:
    - active: tenant bisa login & transaksi
    - suspended: tidak bisa login (get_current_user reject), data tetap
    - archived: tidak bisa login, data retained untuk audit

    is_active sinkron dengan status (backward compat).
    """
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    if payload.status not in ("active", "suspended", "archived"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Status harus 'active', 'suspended', atau 'archived'",
        )

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    old_status = target.status
    target.status = payload.status
    target.is_active = (payload.status == "active")

    _audit_admin_change(
        db, target.id, current["id"], "STATUS_CHANGED",
        f"{old_status} -> {payload.status} | reason={payload.reason or '-'}",
    )
    db.commit()
    db.refresh(target)

    # T24: Notify ALL users in target tenant about status change
    from app.models.user import User
    from app.services.notification_service import create_notification, EventType

    affected_users = (
        db.query(User)
        .filter(User.tenant_id == target.id, User.is_active == True)  # noqa: E712
        .all()
    )
    if payload.status == "suspended":
        event_type = EventType.TENANT_SUSPENDED
        title = "Jemaat di-suspend"
        message = (
            f"Jemaat {target.nama_jemaat_lokal} di-suspend oleh Admin Uni. "
            f"Login & transaksi tidak akan berfungsi hingga di-aktifkan kembali. "
            f"Alasan: {payload.reason or '-'}"
        )
    elif payload.status == "active":
        event_type = EventType.TENANT_ACTIVATED
        title = "Jemaat diaktifkan"
        message = (
            f"Jemaat {target.nama_jemaat_lokal} telah diaktifkan kembali. "
            f"Anda bisa login & melakukan transaksi."
        )
    else:  # archived
        event_type = EventType.TENANT_SUSPENDED  # reuse suspended icon
        title = "Jemaat diarsipkan"
        message = (
            f"Jemaat {target.nama_jemaat_lokal} diarsipkan. "
            f"Login tidak akan berfungsi, data dipertahankan untuk audit."
        )

    for u in affected_users:
        create_notification(
            db,
            user_id=u.id,
            tenant_id=target.id,
            event_type=event_type,
            title=title,
            message=message,
            link="/login",
            related_entity_type="tenant",
            related_entity_id=str(target.id),
            actor_user_id=current["id"],
            commit=False,
        )
    db.commit()

    return _tenant_to_out(target)


# ===== ADMIN UNI: PLAN CHANGE =====

@router.patch("/{tenant_id}/plan", tags=['Tenants'], response_model=TenantOut)
def change_tenant_plan(
    tenant_id: int,
    payload: PlanChangeIn,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Change tenant plan (free / standard / premium). ADMIN_UNI only."""
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    if payload.plan not in ("free", "standard", "premium"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Plan harus 'free', 'standard', atau 'premium'",
        )

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    old_plan = target.plan
    target.plan = payload.plan

    _audit_admin_change(
        db, target.id, current["id"], "PLAN_CHANGED",
        f"{old_plan} -> {payload.plan} | reason={payload.reason or '-'}",
    )
    db.commit()
    db.refresh(target)
    return _tenant_to_out(target)


# ===== Branding Schemas (Tahap 21) =====

class BrandingUpdateIn(BaseModel):
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    footer_text: Optional[str] = None


class BrandingOut(BaseModel):
    logo_url: Optional[str]
    primary_color: str
    secondary_color: str
    footer_text: Optional[str]
    branding_updated_at: Optional[str]
    branding_updated_by: Optional[int]


class LogoUploadOut(BaseModel):
    status: str
    logo_url: str
    size_bytes: int
    message: str


# ===== Branding endpoints (Tahap 21) =====

@router.patch("/{tenant_id}/branding", tags=['Tenants'], response_model=BrandingOut)
def update_branding_endpoint(
    tenant_id: int,
    payload: BrandingUpdateIn,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Update branding (primary_color, secondary_color, footer_text).
    ADMIN_UNI: full access. Others: 403.
    """
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    # Validate colors dulu sebelum apply
    if payload.primary_color is not None:
        try:
            _validate_hex_color(payload.primary_color)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if payload.secondary_color is not None:
        try:
            _validate_hex_color(payload.secondary_color)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    try:
        update_branding(
            db, target,
            primary_color=payload.primary_color,
            secondary_color=payload.secondary_color,
            footer_text=payload.footer_text,
            actor_user_id=current["id"],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    db.commit()
    db.refresh(target)
    return BrandingOut(**get_tenant_branding_dict(target))


@router.get("/{tenant_id}/branding", tags=['Tenants'], response_model=BrandingOut)
def get_branding_endpoint(
    tenant_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Get branding info. Any authenticated user (scope by tenant)."""
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    # User hanya boleh lihat branding tenant sendiri
    if target.id != current["tenant_id"]:
        # ADMIN_UNI bisa lihat branding tenant di uni-nya
        if current["role"] != "ADMIN_UNI":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan tenant Anda")
        caller_uni = _caller_uni(db, current)
        if target.nama_uni != caller_uni.nama_resmi:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")
    return BrandingOut(**get_tenant_branding_dict(target))


@router.post("/{tenant_id}/logo", tags=['Tenants'], response_model=LogoUploadOut)
async def upload_logo_endpoint(
    tenant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Upload logo tenant. Validates:
    - File size <= 1MB
    - MIME type PNG/JPG/SVG
    - Auto-resize jika dimensi > 512px
    """
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    # Read file
    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File kosong")

    # FASE 3-S2.T1 — magic byte validation (mengganti trust terhadap
    # `file.content_type` yang berasal dari client — bisa di-spoof).
    detected_mime = validate_logo(content, file.filename)
    # Pakai detected_mime bukan client-provided untuk konsistensi.
    safe_content_type = detected_mime

    try:
        upload_logo(
            db, target,
            file_content=content,
            filename=file.filename or "logo",
            content_type=safe_content_type,
            actor_user_id=current["id"],
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    db.commit()
    db.refresh(target)
    return LogoUploadOut(
        status="uploaded",
        logo_url=target.logo_url,
        size_bytes=len(content),
        message="Logo berhasil di-upload",
    )


@router.delete("/{tenant_id}/logo", tags=['Tenants'], response_model=BrandingOut)
def delete_logo_endpoint(
    tenant_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Remove logo tenant (revert to default)."""
    if current["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_uni = _caller_uni(db, current)
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    if target.nama_uni != caller_uni.nama_resmi:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant di luar Uni Anda")

    # Hapus file
    if target.logo_url:
        logo_path = STORAGE_ROOT / target.logo_url.lstrip("/")
        if logo_path.exists():
            logo_path.unlink(missing_ok=True)
        target.logo_url = None
        target.branding_updated_at = None
        target.branding_updated_by = None

        _audit_admin_change(
            db, target.id, current["id"], "LOGO_REMOVED",
            target.logo_url or "-",
        )
        db.commit()
        db.refresh(target)

    return BrandingOut(**get_tenant_branding_dict(target))


@router.get("/logo/{tenant_id}", tags=['Tenants'])
def get_logo_endpoint(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    """
    Serve logo file. Public (no auth) agar bisa di-load oleh img tag.
    Kalau tenant suspended/archived, logo tetap served (read-only branding).
    """
    target = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")
    logo_path = get_logo_path(target)
    if not logo_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Logo tidak ditemukan")
    return FileResponse(logo_path)

