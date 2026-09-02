"""
FLIPUS v1.1 — Master data endpoints (public untuk form registrasi).

GET    /api/v1/master/uni                          → list 3 Uni
GET    /api/v1/master/misi?uni_id=X                → list Misi filter Uni
GET    /api/v1/master/misi (no param)              → list all Misi
GET    /api/v1/master/persentase                   → get PersentaseConfig (by scope)
POST   /api/v1/master/persentase                   → update PersentaseConfig (AUDITOR_MISI / ADMIN_UNI)
POST   /api/v1/master/seed                         → seed 3 Uni + 12 Misi (Jerry-only)
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.cache import cached, invalidate_cache
from app.core.security import require_admin_bootstrap_dependency
from app.api.v1.auth import get_current_user
from app.models.master import Uni, MisiKonferens, PersentaseConfig
from app.models.tenant import Tenant
from app.models.audit import AuditLog

router = APIRouter()


class UniOut(BaseModel):
    id: int
    kode: str
    nama_resmi: str

    model_config = ConfigDict(from_attributes=True)


class MisiOut(BaseModel):
    id: int
    uni_id: int
    kode: str
    nama_resmi: str
    jenis: str  # KONFERENS / MISI

    model_config = ConfigDict(from_attributes=True)


@router.get("/uni", response_model=List[UniOut])
def list_uni(db: Session = Depends(get_db)):
    """Public — list 3 Uni untuk dropdown form registrasi."""
    # Cache 10 menit — Uni jarang berubah
    return _cached_list_uni(db)


@cached(ttl_seconds=600)
def _cached_list_uni(db: Session):
    return db.query(Uni).order_by(Uni.id).all()


@router.get("/misi", response_model=List[MisiOut])
def list_misi(
    uni_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Public — list Misi. Filter by uni_id jika ada."""
    return _cached_list_misi(db, uni_id)


@cached(ttl_seconds=600)
def _cached_list_misi(db: Session, uni_id: Optional[int] = None):
    q = db.query(MisiKonferens)
    if uni_id is not None:
        q = q.filter(MisiKonferens.uni_id == uni_id)
    return q.order_by(MisiKonferens.jenis, MisiKonferens.kode).all()


# ===== SEED ENDPOINT (Jerry-only: dilindungi license guard via get_current_user) =====

# Seed data (3 Uni + 12 Misi)
SEED_UNI = [
    ("UIKT", "Gereja Masehi Advent Hari Ketujuh Uni Konferens Indonesia Kawasan Timur"),
    ("UIKB", "Gereja Masehi Advent Hari Ketujuh Uni Indonesia Kawasan Barat"),
    ("UIKC", "Gereja Masehi Advent Hari Ketujuh Uni Indonesia Kawasan Tengah"),
]

# (kode, nama_resmi, jenis, uni_kode)
SEED_MISI = [
    # UIKT
    ("DKM",  "Daerah Konferens Minahasa",                                 "KONFERENS", "UIKT"),
    ("DMML", "Daerah Konferens Manado & Maluku Utara",                    "KONFERENS", "UIKT"),
    ("DKSST", "Daerah Konferens Sulawesi Selatan, Barat dan Tenggara",   "KONFERENS", "UIKT"),
    # UIKB
    ("DBMG", "Daerah Misi Bolmong, Modoinding & Gorontalo",               "MISI",      "UIKB"),
    ("DST",  "Daerah Misi Sulawesi Tengah",                                "MISI",      "UIKB"),
    ("DLTT", "Daerah Misi Luwu Tanah Toraja",                              "MISI",      "UIKB"),
    ("DM",   "Daerah Misi Maluku",                                         "MISI",      "UIKB"),
    # UIKC
    ("DMKB", "Daerah Misi Minahasa & Kota Bitung",                         "MISI",      "UIKC"),
    ("DP",   "Daerah Misi Papua",                                          "MISI",      "UIKC"),
    ("DNU",  "Daerah Misi Nusa Utara",                                     "MISI",      "UIKC"),
    ("DPB",  "Daerah Misi Papua Barat",                                    "MISI",      "UIKC"),
    ("DPBD", "Daerah Misi Papua Barat Daya",                               "MISI",      "UIKC"),
    ("DPT",  "Daerah Misi Papua Tengah",                                   "MISI",      "UIKC"),
]


class SeedOut(BaseModel):
    status: str
    uni_inserted: int
    misi_inserted: int
    skipped: int


@router.post("/seed", response_model=SeedOut)
def seed_master_data(
    db: Session = Depends(get_db),
    _: bool = Depends(require_admin_bootstrap_dependency),
):
    """
    Seed 3 Uni + 12 Misi. Idempotent — kalau sudah ada, skip.

    SECURITY: Wajib header `X-Admin-Token` cocok dengan ADMIN_BOOTSTRAP_TOKEN di .env.
    Generate token: `python3 -c "import secrets; print(secrets.token_hex(32))"`
    """
    uni_inserted = 0
    misi_inserted = 0
    skipped = 0

    # Seed Uni
    for kode, nama in SEED_UNI:
        existing = db.query(Uni).filter(Uni.kode == kode).first()
        if existing:
            skipped += 1
            continue
        db.add(Uni(kode=kode, nama_resmi=nama))
        uni_inserted += 1
    db.flush()

    # Seed Misi
    for kode, nama, jenis, uni_kode in SEED_MISI:
        uni = db.query(Uni).filter(Uni.kode == uni_kode).first()
        if not uni:
            skipped += 1
            continue
        existing = db.query(MisiKonferens).filter(MisiKonferens.kode == kode).first()
        if existing:
            skipped += 1
            continue
        db.add(MisiKonferens(
            kode=kode, nama_resmi=nama, jenis=jenis, uni_id=uni.id,
        ))
        misi_inserted += 1
    db.commit()

    # Invalidate master data cache setelah seed
    invalidate_cache()

    return SeedOut(
        status="ok",
        uni_inserted=uni_inserted,
        misi_inserted=misi_inserted,
        skipped=skipped,
    )


# ===== Persentase Config (T28) =====

class PersentaseConfigOut(BaseModel):
    id: int
    scope: str  # MISI / UNI
    ref_id: int  # misi_konferens.id atau uni.id
    pct_x_jemaat: float
    pct_pt_jemaat: float
    pct_khusus_jemaat: float
    pct_x_uni: float
    pct_pt_uni: float
    pct_khusus_uni: float
    updated_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class PersentaseConfigIn(BaseModel):
    """Input untuk update PersentaseConfig."""
    scope: str = Field(..., description="MISI atau UNI")
    ref_id: int = Field(..., description="id MisiKonferens (jika MISI) atau id Uni (jika UNI)")
    pct_x_jemaat: float = Field(..., ge=0.0, le=1.0)
    pct_pt_jemaat: float = Field(..., ge=0.0, le=1.0)
    pct_khusus_jemaat: float = Field(..., ge=0.0, le=1.0)
    pct_x_uni: float = Field(0.0, ge=0.0, le=1.0)
    pct_pt_uni: float = Field(0.0, ge=0.0, le=1.0)
    pct_khusus_uni: float = Field(0.0, ge=0.0, le=1.0)


def _caller_uni_for_master(db: Session, current: dict) -> Uni:
    """Resolve Uni dari tenant caller. ADMIN_UNI only."""
    tenant = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()
    if not tenant or not tenant.nama_uni:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait Uni")
    uni = db.query(Uni).filter(Uni.nama_resmi == tenant.nama_uni).first()
    if not uni:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uni tidak ditemukan")
    return uni


def _caller_misi_for_master(db: Session, current: dict) -> MisiKonferens:
    """Resolve Misi dari tenant caller. AUDITOR_MISI only."""
    tenant = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()
    if not tenant or not tenant.misi_konferens_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait Misi")
    misi = db.query(MisiKonferens).filter(MisiKonferens.id == tenant.misi_konferens_id).first()
    if not misi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Misi tidak ditemukan")
    return misi


@router.get("/persentase", response_model=PersentaseConfigOut)
def get_persentase_config(
    scope: str,
    ref_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Get PersentaseConfig.
    - AUDITOR_MISI: hanya bisa lihat config MISI scope di misi-nya
    - ADMIN_UNI: bisa lihat config MISI atau UNI scope di uni-nya
    """
    if scope not in ("MISI", "UNI"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope harus 'MISI' atau 'UNI'")

    if current["role"] == "AUDITOR_MISI":
        caller_misi = _caller_misi_for_master(db, current)
        if scope == "MISI":
            if ref_id != caller_misi.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan misi Anda")
        elif scope == "UNI":
            # Auditor boleh VIEW (read-only) persentase UNI dari uni yang menaungi misinya
            if ref_id != caller_misi.uni_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan uni Anda")
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope harus 'MISI' atau 'UNI'")
    elif current["role"] == "ADMIN_UNI":
        caller_uni = _caller_uni_for_master(db, current)
        if scope == "UNI":
            if ref_id != caller_uni.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan uni Anda")
        elif scope == "MISI":
            misi = db.query(MisiKonferens).filter(MisiKonferens.id == ref_id).first()
            if not misi or misi.uni_id != caller_uni.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Misi di luar uni Anda")
    elif current["role"] in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA"):
        # T39: jemaat-level boleh lihat MISI scope (read-only) untuk misi tenant-nya
        # (supaya dasbor Bendahara/Ketua/Pendeta bisa menampilkan persentase
        # yang ditetapkan Auditor Misi).
        if scope != "MISI":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Jemaat hanya boleh lihat MISI scope")
        caller_tenant = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()
        if not caller_tenant or not caller_tenant.misi_konferens_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait Misi")
        if ref_id != caller_tenant.misi_konferens_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan misi Anda")
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Auditor Misi / Admin Uni")

    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == scope, PersentaseConfig.ref_id == ref_id)
        .first()
    )
    if not cfg:
        # Default fallback (kalau belum pernah di-set)
        cfg = PersentaseConfig(
            scope=scope, ref_id=ref_id,
            pct_x_jemaat=1.0, pct_pt_jemaat=0.5, pct_khusus_jemaat=0.5,
            pct_x_uni=0.0, pct_pt_uni=0.0, pct_khusus_uni=0.0,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    return PersentaseConfigOut(
        id=cfg.id,
        scope=cfg.scope,
        ref_id=cfg.ref_id,
        pct_x_jemaat=cfg.pct_x_jemaat,
        pct_pt_jemaat=cfg.pct_pt_jemaat,
        pct_khusus_jemaat=cfg.pct_khusus_jemaat,
        pct_x_uni=cfg.pct_x_uni,
        pct_pt_uni=cfg.pct_pt_uni,
        pct_khusus_uni=cfg.pct_khusus_uni,
        updated_at=str(cfg.updated_at) if cfg.updated_at else None,
    )


@router.post("/persentase", response_model=PersentaseConfigOut)
def update_persentase_config(
    payload: PersentaseConfigIn,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Update PersentaseConfig. RBAC sama seperti GET.

    Audit: catat sebelum-sesudah persentase untuk transparansi ke jemaat.
    Tidak auto-recompute kuitansi existing — porsi yang sudah tersimpan tetap.
    Untuk recompute kuitansi existing, gunakan endpoint /v1/admin/recompute-porsi (Jerry-only).
    """
    if payload.scope not in ("MISI", "UNI"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope harus 'MISI' atau 'UNI'")

    # T86 DEBUG (2026-08-23): Log role untuk diagnose error "Hanya Auditor..."
    import sys
    print(f"[DEBUG master.py POST] user_id={current.get('id')} role={current.get('role')!r} tenant_id={current.get('tenant_id')} scope={payload.scope} ref_id={payload.ref_id} pj_x={payload.pct_x_jemaat}", file=sys.stderr, flush=True)

    if current["role"] == "AUDITOR_MISI":
        if payload.scope != "MISI":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Auditor hanya boleh edit config MISI")
        caller_misi = _caller_misi_for_master(db, current)
        if payload.ref_id != caller_misi.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan misi Anda")
    elif current["role"] == "ADMIN_UNI":
        caller_uni = _caller_uni_for_master(db, current)
        if payload.scope == "UNI":
            if payload.ref_id != caller_uni.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Bukan uni Anda")
        elif payload.scope == "MISI":
            misi = db.query(MisiKonferens).filter(MisiKonferens.id == payload.ref_id).first()
            if not misi or misi.uni_id != caller_uni.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Misi di luar uni Anda")
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Auditor Misi / Admin Uni")

    # Get or create
    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == payload.scope, PersentaseConfig.ref_id == payload.ref_id)
        .first()
    )
    if not cfg:
        cfg = PersentaseConfig(
            scope=payload.scope,
            ref_id=payload.ref_id,
        )
        db.add(cfg)

    # Capture before (untuk audit)
    before = (
        f"x={cfg.pct_x_jemaat},pt={cfg.pct_pt_jemaat},kh={cfg.pct_khusus_jemaat}|"
        f"x_u={cfg.pct_x_uni},pt_u={cfg.pct_pt_uni},kh_u={cfg.pct_khusus_uni}"
    )

    # T81 (revisi 2026-08-23): Validasi range Jerry Model B — pct_uni adalah
    # fraction of (1 - pct_jemaat), bukan of total. Constraint pct_jemaat +
    # pct_uni ≤ 1.0 sudah TIDAK berlaku lagi (Model A strict). Hanya cek range 0..1.
    from app.utils.porsi_calculator import validate_porsi_constraint
    errs = validate_porsi_constraint(
        pct_x_jemaat=payload.pct_x_jemaat, pct_x_uni=payload.pct_x_uni,
        pct_pt_jemaat=payload.pct_pt_jemaat, pct_pt_uni=payload.pct_pt_uni,
        pct_khusus_jemaat=payload.pct_khusus_jemaat, pct_khusus_uni=payload.pct_khusus_uni,
    )

    # T105 (2026-08-26): Cross-scope validation — Jerry Model B butuh total
    # pct_jemaat + pct_uni ≤ 1.0. pct_uni bisa di UNI scope (Admin Uni set).
    # Save MISI scope saja tidak bisa valid kalau pct_jemaat + UNI pct_uni > 1.0.
    if payload.scope == "MISI" and current["role"] == "AUDITOR_MISI":
        misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == payload.ref_id).first()
        if misi_row:
            uni_cfg = (
                db.query(PersentaseConfig)
                .filter(PersentaseConfig.scope == "UNI", PersentaseConfig.ref_id == misi_row.uni_id)
                .first()
            )
            uni_x = float(uni_cfg.pct_x_uni or 0) if uni_cfg else 0
            uni_pt = float(uni_cfg.pct_pt_uni or 0) if uni_cfg else 0
            uni_kh = float(uni_cfg.pct_khusus_uni or 0) if uni_cfg else 0
            tiers = [
                ("X",      payload.pct_x_jemaat,      uni_x),
                ("PT",     payload.pct_pt_jemaat,     uni_pt),
                ("Khusus", payload.pct_khusus_jemaat, uni_kh),
            ]
            for tier_name, pj, pu in tiers:
                if pj + pu > 1.0 + 1e-9:
                    errs.append(
                        f"{tier_name}: Anda set {(1-pj)*100:.0f}% ke Misi, "
                        f"Admin Uni set {pu*100:.0f}% ke Uni. "
                        f"Total {pj*100+pu*100:.0f}% > 100%. "
                        f"Kurangi slider Misi atau minta Admin Uni kurangi slider Uni."
                    )

    # T105 (2026-08-26): Cross-scope dari sisi Admin Uni — kalau Admin Uni save
    # pct_uni, cross-check dengan pct_jemaat di semua MISI scopes dalam uni ini.
    if payload.scope == "UNI" and current["role"] == "ADMIN_UNI":
        misi_rows = db.query(MisiKonferens).filter(MisiKonferens.uni_id == payload.ref_id).all()
        for misi_row in misi_rows:
            misi_cfg = (
                db.query(PersentaseConfig)
                .filter(PersentaseConfig.scope == "MISI", PersentaseConfig.ref_id == misi_row.id)
                .first()
            )
            if not misi_cfg:
                continue
            pj_x = float(misi_cfg.pct_x_jemaat or 0)
            pj_pt = float(misi_cfg.pct_pt_jemaat or 0)
            pj_kh = float(misi_cfg.pct_khusus_jemaat or 0)
            tiers = [
                ("X",      pj_x, payload.pct_x_uni),
                ("PT",     pj_pt, payload.pct_pt_uni),
                ("Khusus", pj_kh, payload.pct_khusus_uni),
            ]
            for tier_name, pj, pu in tiers:
                if pj + pu > 1.0 + 1e-9:
                    errs.append(
                        f"{tier_name}: Misi {misi_row.kode} set {(1-pj)*100:.0f}% ke Misi, "
                        f"Anda set {pu*100:.0f}% ke Uni. "
                        f"Total {pj*100+pu*100:.0f}% > 100%. "
                        f"Kurangi slider Uni atau minta Auditor Misi kurangi slider Misi."
                    )

    if errs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Persentase tidak valid: " + " | ".join(errs),
        )

    # Update
    cfg.pct_x_jemaat = payload.pct_x_jemaat
    cfg.pct_pt_jemaat = payload.pct_pt_jemaat
    cfg.pct_khusus_jemaat = payload.pct_khusus_jemaat
    cfg.pct_x_uni = payload.pct_x_uni
    cfg.pct_pt_uni = payload.pct_pt_uni
    cfg.pct_khusus_uni = payload.pct_khusus_uni

    after = (
        f"x={cfg.pct_x_jemaat},pt={cfg.pct_pt_jemaat},kh={cfg.pct_khusus_jemaat}|"
        f"x_u={cfg.pct_x_uni},pt_u={cfg.pct_pt_uni},kh_u={cfg.pct_khusus_uni}"
    )

    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"PERSENTASE_UPDATED_scope_{payload.scope}_ref_{payload.ref_id}_by_user_{current['id']}",
        payload_hash=f"before={before} -> after={after}",
    ))
    db.commit()
    db.refresh(cfg)

    # Invalidate cache supaya dashboard langsung reflect perubahan
    invalidate_cache()

    return PersentaseConfigOut(
        id=cfg.id,
        scope=cfg.scope,
        ref_id=cfg.ref_id,
        pct_x_jemaat=cfg.pct_x_jemaat,
        pct_pt_jemaat=cfg.pct_pt_jemaat,
        pct_khusus_jemaat=cfg.pct_khusus_jemaat,
        pct_x_uni=cfg.pct_x_uni,
        pct_pt_uni=cfg.pct_pt_uni,
        pct_khusus_uni=cfg.pct_khusus_uni,
        updated_at=str(cfg.updated_at) if cfg.updated_at else None,
    )
