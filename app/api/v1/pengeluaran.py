"""
v2.0 M5 — Router Pengeluaran + KategoriPengeluaran + dual-stage approval.

Endpoints:
- GET    /api/v1/kategori-pengeluaran/list        — List kategori aktif untuk tenant user
- POST   /api/v1/kategori-pengeluaran/create      — Tambah kategori (BENDAHARA only)
- GET    /api/v1/pengeluaran/list                — List pengeluaran (filter tenant + status + tanggal)
- POST   /api/v1/pengeluaran/create              — Create draft (BENDAHARA only)
- PUT    /api/v1/pengeluaran/{id}/update         — Update draft (BENDAHARA only, status=draft only)
- POST   /api/v1/pengeluaran/{id}/submit         — Submit draft → if rutin → approved, else pending_approval
- POST   /api/v1/pengeluaran/{id}/approve-ketua  — Ketua approve → status=approved_ketua
- POST   /api/v1/pengeluaran/{id}/approve-pendeta— Pendeta approve → status=approved
- POST   /api/v1/pengeluaran/{id}/reject         — Reject (Ketua/Pendeta) dengan reason
- GET    /api/v1/pengeluaran/rekap               — Rekap bulanan (untuk dashboard widget)
- GET    /api/v1/pengeluaran/pending-count       — Count pending approval (untuk Ketua/Pendeta badge)

Approval chain (Jerry 2026-09-01):
- Rutin (kategori.is_rutin=True: Listrik/Air/Telpon/Gaji Kostor) → auto-approved Bendahara
- Non-rutin → Bendahara submit → Ketua approve → Pendeta approve → LOCKED
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.api.v1.auth import require_roles
from app.core.database import get_db
from app.core.tenant_scope import (
    TenantScope,
    require_tenant_scope,
)
from app.models.kategori_pengeluaran import KategoriPengeluaran
from app.models.pengeluaran import Pengeluaran

router = APIRouter()


# ========== Schemas ==========

class KategoriPengeluaranOut(BaseModel):
    id: int
    nama: str
    alias: str
    is_rutin: bool
    urutan: int

    model_config = ConfigDict(from_attributes=True)


class KategoriPengeluaranCreate(BaseModel):
    nama: str = Field(..., min_length=2, max_length=50)
    alias: str = Field(..., min_length=2, max_length=8)
    is_rutin: bool = False


class PengeluaranOut(BaseModel):
    id: int
    nomor_pengeluaran: str
    tanggal: str
    tanggal_sabat: str
    kategori_pengeluaran_id: int
    kategori_nama: str | None = None
    kategori_alias: str | None = None
    jumlah: int
    deskripsi: str | None = None
    penerima: str | None = None
    metode_bayar: str | None = None
    status: str
    created_via: str | None = None
    created_by_user_id: int | None = None
    created_at: str
    approved_ketua_at: str | None = None
    approved_pendeta_at: str | None = None
    rejected_at: str | None = None
    rejected_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class PengeluaranCreate(BaseModel):
    tanggal: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    kategori_pengeluaran_id: int
    jumlah: int = Field(..., gt=0)
    deskripsi: str | None = Field(None, max_length=500)
    penerima: str | None = Field(None, max_length=200)
    metode_bayar: str | None = Field(None, max_length=20)


class PengeluaranUpdate(BaseModel):
    tanggal: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    kategori_pengeluaran_id: int | None = None
    jumlah: int | None = Field(None, gt=0)
    deskripsi: str | None = Field(None, max_length=500)
    penerima: str | None = Field(None, max_length=200)
    metode_bayar: str | None = Field(None, max_length=20)


class PengeluaranAction(BaseModel):
    note: str | None = Field(None, max_length=255)


class PengeluaranReject(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class RekapBulananOut(BaseModel):
    bulan: str  # YYYY-MM
    total_rutin: int
    total_non_rutin: int
    total: int
    count_rutin: int
    count_non_rutin: int
    count_pending: int
    by_kategori: list[dict]  # [{kategori_id, kategori_nama, total, count}]


# ========== Helpers ==========

def _generate_nomor_pengeluaran(db: Session, tenant_id: int, tanggal_iso: str) -> str:
    """Generate nomor pengeluaran: OUT-{YYYYMMDD}-{seq3}"""
    ymd = tanggal_iso.replace("-", "")
    prefix = f"OUT-{ymd}-"
    last = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.nomor_pengeluaran.like(f"{prefix}%"))
        .order_by(desc(Pengeluaran.nomor_pengeluaran))
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.nomor_pengeluaran.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:03d}"


def _get_sabat_for_tanggal(db: Session, tenant_id: int, tanggal_iso: str) -> tuple:
    """Return (id_rekap_mingguan, tanggal_sabat) untuk tanggal.
    Menggunakan pattern dari T111 — cari sabat terakhir <= tanggal untuk tenant.
    Simplified: pakai tanggal itu sendiri sebagai sabat_date (fallback).
    Real implementation akan lookup rekap_mingguan table — untuk M5, pakai placeholder.
    """
    # TODO: Implement proper rekap_mingguan lookup
    # For M5 MVP: pakai tanggal_sabat = tanggal
    return (f"RK-{tanggal_iso[:7]}", tanggal_iso)


def _kategori_to_dict(k: KategoriPengeluaran) -> dict:
    return {"id": k.id, "nama": k.nama, "alias": k.alias, "is_rutin": k.is_rutin, "urutan": k.urutan}


def _pengeluaran_to_dict(p: Pengeluaran, kategori: KategoriPengeluaran | None) -> dict:
    return {
        "id": p.id,
        "nomor_pengeluaran": p.nomor_pengeluaran,
        "tanggal": p.tanggal,
        "tanggal_sabat": p.tanggal_sabat,
        "kategori_pengeluaran_id": p.kategori_pengeluaran_id,
        "kategori_nama": kategori.nama if kategori else None,
        "kategori_alias": kategori.alias if kategori else None,
        "jumlah": p.jumlah,
        "deskripsi": p.deskripsi,
        "penerima": p.penerima,
        "metode_bayar": p.metode_bayar,
        "status": p.status,
        "created_via": p.created_via,
        "created_by_user_id": p.created_by_user_id,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "approved_ketua_at": p.approved_ketua_at.isoformat() if p.approved_ketua_at else None,
        "approved_pendeta_at": p.approved_pendeta_at.isoformat() if p.approved_pendeta_at else None,
        "rejected_at": p.rejected_at.isoformat() if p.rejected_at else None,
        "rejected_reason": p.rejected_reason,
    }


# ========== KategoriPengeluaran endpoints ==========

@router.get("/kategori-pengeluaran/list", tags=['Pengeluaran'], response_model=list[KategoriPengeluaranOut])
def list_kategori_pengeluaran(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """v2.0 M5 — List kategori pengeluaran aktif untuk tenant user.

    FASE4-S6D: pakai TenantScope (gantikan inline tenant_id = current_user).
    """
    rows = (
        db.query(KategoriPengeluaran)
        .filter(KategoriPengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(KategoriPengeluaran.is_aktif == True)  # noqa: E712
        .order_by(
            KategoriPengeluaran.is_rutin.desc(),
            KategoriPengeluaran.urutan.asc(),
            KategoriPengeluaran.nama.asc(),
        )
        .limit(100)
        .all()
    )
    return [KategoriPengeluaranOut.model_validate(_kategori_to_dict(r)) for r in rows]


@router.post("/kategori-pengeluaran/create", tags=['Pengeluaran'], response_model=KategoriPengeluaranOut, status_code=201)
def create_kategori_pengeluaran(
    payload: KategoriPengeluaranCreate,
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("BENDAHARA")),
):
    """v2.0 M5 — Tambah kategori pengeluaran (BENDAHARA only)."""
    tenant_id = current.get("tenant_id")
    if not tenant_id:
        raise HTTPException(400, "User tidak terkait dengan tenant/jemaat")

    alias_upper = payload.alias.upper().strip()
    # Check duplikat
    existing = (
        db.query(KategoriPengeluaran)
        .filter(KategoriPengeluaran.tenant_id == tenant_id)
        .filter(KategoriPengeluaran.alias == alias_upper)
        .first()
    )
    if existing:
        raise HTTPException(409, f"Alias '{alias_upper}' sudah ada di jemaat ini")

    # Smart urutan: MAX + 1
    max_urutan = (
        db.query(sqlfunc.max(KategoriPengeluaran.urutan))
        .filter(KategoriPengeluaran.tenant_id == tenant_id)
        .scalar()
    )
    urutan = (max_urutan or 0) + 1

    k = KategoriPengeluaran(
        tenant_id=tenant_id,
        nama=payload.nama.strip(),
        alias=alias_upper,
        is_rutin=payload.is_rutin,
        urutan=urutan,
        is_aktif=True,
    )
    db.add(k)
    db.commit()
    db.refresh(k)
    return KategoriPengeluaranOut.model_validate(_kategori_to_dict(k))


# ========== Pengeluaran endpoints ==========

@router.get("/pengeluaran/list", tags=['Pengeluaran'], response_model=list[PengeluaranOut])
def list_pengeluaran(
    status_filter: str | None = None,
    bulan: str | None = None,  # YYYY-MM
    limit: int = 100,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """v2.0 M5 — List pengeluaran (filter tenant + optional status + optional bulan).

    FASE4-S6D: pakai TenantScope (gantikan inline tenant_id = current_user).
    """
    q = db.query(Pengeluaran).filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
    if status_filter:
        q = q.filter(Pengeluaran.status == status_filter)
    if bulan:
        q = q.filter(Pengeluaran.tanggal.like(f"{bulan}%"))
    rows = q.order_by(desc(Pengeluaran.tanggal), desc(Pengeluaran.id)).limit(limit).all()

    # Lookup kategori in bulk
    kat_ids = {r.kategori_pengeluaran_id for r in rows}
    kat_map = {}
    if kat_ids:
        kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id.in_(kat_ids)).all()
        kat_map = {k.id: k for k in kats}

    return [PengeluaranOut.model_validate(_pengeluaran_to_dict(r, kat_map.get(r.kategori_pengeluaran_id))) for r in rows]


@router.post("/pengeluaran/create", tags=['Pengeluaran'], response_model=PengeluaranOut, status_code=201)
def create_pengeluaran(
    payload: PengeluaranCreate,
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("BENDAHARA")),
):
    """v2.0 M5 — Create draft pengeluaran (BENDAHARA only). Status='draft'. Submit terpisah."""
    tenant_id = current.get("tenant_id")
    user_id = current.get("id")
    if not tenant_id or not user_id:
        raise HTTPException(400, "User invalid (no tenant/user_id)")

    # Validate kategori exists di tenant
    kat = (
        db.query(KategoriPengeluaran)
        .filter(KategoriPengeluaran.tenant_id == tenant_id)
        .filter(KategoriPengeluaran.id == payload.kategori_pengeluaran_id)
        .filter(KategoriPengeluaran.is_aktif == True)  # noqa: E712
        .first()
    )
    if not kat:
        raise HTTPException(404, f"Kategori id={payload.kategori_pengeluaran_id} tidak ditemukan di jemaat ini")

    id_rekap, tanggal_sabat = _get_sabat_for_tanggal(db, tenant_id, payload.tanggal)
    nomor = _generate_nomor_pengeluaran(db, tenant_id, payload.tanggal)

    p = Pengeluaran(
        tenant_id=tenant_id,
        id_rekap_mingguan=id_rekap,
        nomor_pengeluaran=nomor,
        tanggal=payload.tanggal,
        tanggal_sabat=tanggal_sabat,
        kategori_pengeluaran_id=payload.kategori_pengeluaran_id,
        jumlah=payload.jumlah,
        deskripsi=payload.deskripsi,
        penerima=payload.penerima,
        metode_bayar=payload.metode_bayar,
        status='draft',
        created_by_user_id=user_id,
        created_via='web',
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.put("/pengeluaran/{pengeluaran_id}/update", tags=['Pengeluaran'], response_model=PengeluaranOut)
def update_pengeluaran(
    pengeluaran_id: int,
    payload: PengeluaranUpdate,
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("BENDAHARA")),
):
    """v2.0 M5 — Update draft (BENDAHARA, status=draft only)."""
    tenant_id = current.get("tenant_id")
    p = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.id == pengeluaran_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.status != 'draft':
        raise HTTPException(400, f"Hanya status 'draft' yang bisa diedit (saat ini: {p.status})")

    if payload.tanggal is not None:
        p.tanggal = payload.tanggal
        # Recompute sabat
        _id_rekap, p.tanggal_sabat = _get_sabat_for_tanggal(db, tenant_id, payload.tanggal)
        p.id_rekap_mingguan = _id_rekap
    if payload.kategori_pengeluaran_id is not None:
        kat = (
            db.query(KategoriPengeluaran)
            .filter(KategoriPengeluaran.tenant_id == tenant_id)
            .filter(KategoriPengeluaran.id == payload.kategori_pengeluaran_id)
            .filter(KategoriPengeluaran.is_aktif == True)  # noqa: E712
            .first()
        )
        if not kat:
            raise HTTPException(404, f"Kategori id={payload.kategori_pengeluaran_id} tidak ditemukan")
        p.kategori_pengeluaran_id = payload.kategori_pengeluaran_id
    if payload.jumlah is not None:
        p.jumlah = payload.jumlah
    if payload.deskripsi is not None:
        p.deskripsi = payload.deskripsi
    if payload.penerima is not None:
        p.penerima = payload.penerima
    if payload.metode_bayar is not None:
        p.metode_bayar = payload.metode_bayar

    db.commit()
    db.refresh(p)

    kat = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id == p.kategori_pengeluaran_id).first()
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.post("/pengeluaran/{pengeluaran_id}/submit", tags=['Pengeluaran'], response_model=PengeluaranOut)
def submit_pengeluaran(
    pengeluaran_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("BENDAHARA")),
):
    """v2.0 M5 — Submit draft.
    - Kalau kategori.is_rutin=True → auto-approved (status='approved', self-approved)
    - Kalau is_rutin=False → status='pending_approval' (awaiting Ketua)
    """
    tenant_id = current.get("tenant_id")
    user_id = current.get("id")
    p = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.id == pengeluaran_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.status != 'draft':
        raise HTTPException(400, f"Hanya status 'draft' yang bisa disubmit (saat ini: {p.status})")

    kat = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id == p.kategori_pengeluaran_id).first()
    if not kat:
        raise HTTPException(500, "Kategori tidak ditemukan (data inconsistency)")

    now = datetime.utcnow()
    if kat.is_rutin:
        # Auto-approved: Bendahara self-approve both Ketua + Pendeta slots
        p.status = 'approved'
        p.approved_ketua_by_user_id = user_id
        p.approved_ketua_at = now
        p.approved_pendeta_by_user_id = user_id
        p.approved_pendeta_at = now
    else:
        p.status = 'pending_approval'

    db.commit()
    db.refresh(p)
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.post("/pengeluaran/{pengeluaran_id}/approve-ketua", tags=['Pengeluaran'], response_model=PengeluaranOut)
def approve_ketua(
    pengeluaran_id: int,
    payload: PengeluaranAction = PengeluaranAction(),
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("KETUA_KEUANGAN")),
):
    """v2.0 M5 — Ketua approve → status='approved_ketua' (awaiting Pendeta)."""
    tenant_id = current.get("tenant_id")
    user_id = current.get("id")
    p = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.id == pengeluaran_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.status != 'pending_approval':
        raise HTTPException(400, f"Hanya status 'pending_approval' yang bisa di-approve Ketua (saat ini: {p.status})")

    p.status = 'approved_ketua'
    p.approved_ketua_by_user_id = user_id
    p.approved_ketua_at = datetime.utcnow()
    p.approved_ketua_note = payload.note

    db.commit()
    db.refresh(p)
    kat = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id == p.kategori_pengeluaran_id).first()
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.post("/pengeluaran/{pengeluaran_id}/approve-pendeta", tags=['Pengeluaran'], response_model=PengeluaranOut)
def approve_pendeta(
    pengeluaran_id: int,
    payload: PengeluaranAction = PengeluaranAction(),
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("PENDETA")),
):
    """v2.0 M5 — Pendeta approve → status='approved' (LOCKED)."""
    tenant_id = current.get("tenant_id")
    user_id = current.get("id")
    p = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.id == pengeluaran_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.status != 'approved_ketua':
        raise HTTPException(400, f"Hanya status 'approved_ketua' yang bisa di-approve Pendeta (saat ini: {p.status})")

    p.status = 'approved'
    p.approved_pendeta_by_user_id = user_id
    p.approved_pendeta_at = datetime.utcnow()
    p.approved_pendeta_note = payload.note

    db.commit()
    db.refresh(p)
    kat = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id == p.kategori_pengeluaran_id).first()
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.post("/pengeluaran/{pengeluaran_id}/reject", tags=['Pengeluaran'], response_model=PengeluaranOut)
def reject_pengeluaran(
    pengeluaran_id: int,
    payload: PengeluaranReject,
    db: Session = Depends(get_db),
    current: dict = Depends(require_roles("KETUA_KEUANGAN", "PENDETA")),
):
    """v2.0 M5 — Reject (Ketua/Pendeta) dengan reason. Status → 'rejected' (LOCKED)."""
    tenant_id = current.get("tenant_id")
    user_id = current.get("id")
    p = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.tenant_id == tenant_id)
        .filter(Pengeluaran.id == pengeluaran_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "Pengeluaran tidak ditemukan")
    if p.status not in ('pending_approval', 'approved_ketua'):
        raise HTTPException(400, f"Hanya status 'pending_approval' atau 'approved_ketua' yang bisa di-reject (saat ini: {p.status})")

    p.status = 'rejected'
    p.rejected_by_user_id = user_id
    p.rejected_at = datetime.utcnow()
    p.rejected_reason = payload.reason

    db.commit()
    db.refresh(p)
    kat = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id == p.kategori_pengeluaran_id).first()
    return PengeluaranOut.model_validate(_pengeluaran_to_dict(p, kat))


@router.get("/pengeluaran/pending-count", tags=['Pengeluaran'])
def pending_count(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """v2.0 M5 — Count pending approval untuk badge Ketua/Pendeta dashboard.

    FASE4-S6D: pakai TenantScope (gantikan inline tenant_id = current_user).
    """
    pending_ketua = (
        db.query(sqlfunc.count(Pengeluaran.id))
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.status == 'pending_approval')
        .scalar()
    )
    pending_pendeta = (
        db.query(sqlfunc.count(Pengeluaran.id))
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.status == 'approved_ketua')
        .scalar()
    )
    return {"pending_ketua": pending_ketua or 0, "pending_pendeta": pending_pendeta or 0}


@router.get("/pengeluaran/rekap", tags=['Pengeluaran'], response_model=RekapBulananOut)
def rekap_bulanan(
    bulan: str,  # YYYY-MM
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """v2.0 M5 — Rekap bulanan per tenant (untuk dashboard widget).

    FASE4-S6D: pakai TenantScope (gantikan inline tenant_id = current_user).
    """
    if not re.match(r"^\d{4}-\d{2}$", bulan):
        raise HTTPException(400, "Format bulan harus YYYY-MM")

    # Aggregate by kategori
    rows = (
        db.query(
            Pengeluaran.kategori_pengeluaran_id,
            sqlfunc.sum(Pengeluaran.jumlah).label("total"),
            sqlfunc.count(Pengeluaran.id).label("cnt"),
        )
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.tanggal.like(f"{bulan}%"))
        .filter(Pengeluaran.status == "approved")
        .group_by(Pengeluaran.kategori_pengeluaran_id)
        .all()
    )

    # Lookup kategori
    kat_ids = [r.kategori_pengeluaran_id for r in rows]
    kat_map = {}
    if kat_ids:
        kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id.in_(kat_ids)).all()
        kat_map = {k.id: k for k in kats}

    by_kategori = []
    total_rutin = 0
    total_non_rutin = 0
    count_rutin = 0
    count_non_rutin = 0
    for r in rows:
        kat = kat_map.get(r.kategori_pengeluaran_id)
        is_rutin = kat.is_rutin if kat else False
        if is_rutin:
            total_rutin += int(r.total or 0)
            count_rutin += int(r.cnt or 0)
        else:
            total_non_rutin += int(r.total or 0)
            count_non_rutin += int(r.cnt or 0)
        by_kategori.append({
            "kategori_id": r.kategori_pengeluaran_id,
            "kategori_nama": kat.nama if kat else f"#{r.kategori_pengeluaran_id}",
            "kategori_alias": kat.alias if kat else "?",
            "is_rutin": is_rutin,
            "total": int(r.total or 0),
            "count": int(r.cnt or 0),
        })
    by_kategori.sort(key=lambda x: (-x["total"], x["kategori_nama"]))

    # Pending count (any status not approved yet)
    count_pending = (
        db.query(sqlfunc.count(Pengeluaran.id))
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.tanggal.like(f"{bulan}%"))
        .filter(Pengeluaran.status.in_(['pending_approval', 'approved_ketua']))
        .scalar()
    ) or 0

    return RekapBulananOut(
        bulan=bulan,
        total_rutin=total_rutin,
        total_non_rutin=total_non_rutin,
        total=total_rutin + total_non_rutin,
        count_rutin=count_rutin,
        count_non_rutin=count_non_rutin,
        count_pending=count_pending,
        by_kategori=by_kategori,
    )
