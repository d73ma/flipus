"""
FLIPUS v1.1 — Agregat endpoint untuk semua role dashboard (Pendeta, Ketua,
Auditor Misi, Admin Uni).

Return agregat per Minggu/Sabat — untuk tampilan dashboard read-only.

Endpoint:
- GET /agregat/tenant — agregat per minggu untuk tenant caller (Pendeta/Ketua/Bendahara)
- GET /agregat/misi — agregat per minggu untuk SEMUA jemaat di misi caller (Auditor)
- GET /agregat/uni — agregat per minggu untuk SEMUA misi di uni caller (Admin Uni)
- GET /agregat/jemaat — list jemaat + summary (untuk Auditor)
- GET /agregat/misi-list — list misi + summary (untuk Admin Uni)
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.security import decrypt_pii
from app.core.tenant_scope import TenantScope, require_tenant_scope, resolve_tenant_scope
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.master import MisiKonferens, Uni, PersentaseConfig
from app.utils.number_to_words import bilang, terbilang  # noqa
from app.utils.sabat_counter import get_current_sabat

router = APIRouter()


# ===== Schemas =====

class MingguanItem(BaseModel):
    id_rekap_mingguan: str
    tanggal_sabat: str
    jumlah_kuitansi: int
    total_x: int
    total_pt: int
    total_khusus: int
    total_semua: int
    porsi_kantor_misi: int
    porsi_kas_jemaat: int


class AgregatTenantOut(BaseModel):
    tenant_id: int
    nama_jemaat: str
    bulan: Optional[str] = None
    minggu_items: List[MingguanItem]
    grand_total_x: int
    grand_total_pt: int
    grand_total_khusus: int
    grand_total_semua: int
    grand_total_porsi_misi: int
    grand_total_porsi_jemaat: int
    grand_total_huruf: str


class JemaatSummary(BaseModel):
    tenant_id: int
    nama_jemaat: str
    nama_pendeta: Optional[str] = None
    nama_ketua_keuangan: Optional[str] = None
    nama_bendahara: Optional[str] = None
    jumlah_kuitansi: int = 0
    total_x: int = 0
    total_pt: int = 0
    total_khusus: int = 0
    total_porsi_misi: int = 0
    total_porsi_jemaat: int = 0


class AgregatMisiOut(BaseModel):
    misi_id: Optional[int] = None
    nama_misi: str
    bulan: Optional[str] = None
    minggu_items: List[MingguanItem]
    grand_total: int
    grand_total_x: int
    grand_total_pt: int
    grand_total_khusus: int
    grand_total_porsi_misi: int
    grand_total_porsi_jemaat: int
    grand_total_huruf: str
    jemaat_count: int
    jemaat_summary: List[JemaatSummary]


# ===== T47: Live calculation helpers =====
PCT_DEFAULTS_LIVE = {
    "pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.5,
    "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0,
}


def _load_pct_contexts(db: Session, tenant_ids: List[int]) -> tuple[dict, dict, dict]:
    """Pre-load PersentaseConfig (MISI + UNI scope) untuk daftar tenant_ids.

    Returns:
        tenants_map: {tenant_id: Tenant}
        misi_cfg: {misi_id: PersentaseConfig}
        uni_cfg: {uni_id: PersentaseConfig}
    """
    tenants_map = {t.id: t for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}
    unique_misi_ids: set[int] = set()
    for tid in tenants_map.keys():
        t = tenants_map[tid]
        if t.misi_konferens_id:
            unique_misi_ids.add(t.misi_konferens_id)
    unique_uni_ids: set[int] = set()
    if unique_misi_ids:
        misi_rows = db.query(MisiKonferens).filter(MisiKonferens.id.in_(unique_misi_ids)).all()
        for m in misi_rows:
            if m.uni_id:
                unique_uni_ids.add(m.uni_id)
    misi_cfg = {
        c.ref_id: c for c in db.query(PersentaseConfig).filter(
            PersentaseConfig.scope == "MISI",
            PersentaseConfig.ref_id.in_(unique_misi_ids) if unique_misi_ids else [0],
        ).all()
    }
    uni_cfg = {
        c.ref_id: c for c in db.query(PersentaseConfig).filter(
            PersentaseConfig.scope == "UNI",
            PersentaseConfig.ref_id.in_(unique_uni_ids) if unique_uni_ids else [0],
        ).all()
    }
    return tenants_map, misi_cfg, uni_cfg


def _pct_for_tenant_id(
    tenant_id: int,
    tenants_map: dict,
    misi_cfg: dict,
    uni_cfg: dict,
    db: Session,
) -> dict:
    """Resolve effective pct config untuk tenant_id (Layer 1 + Layer 2)."""
    t = tenants_map.get(tenant_id)
    if not t or not t.misi_konferens_id:
        return {**PCT_DEFAULTS_LIVE}
    mcfg = misi_cfg.get(t.misi_konferens_id)
    misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == t.misi_konferens_id).first()
    ucfg = uni_cfg.get(misi_row.uni_id) if misi_row else None
    return {
        "pct_x_jemaat": float(mcfg.pct_x_jemaat if mcfg and mcfg.pct_x_jemaat is not None else PCT_DEFAULTS_LIVE["pct_x_jemaat"]),
        "pct_pt_jemaat": float(mcfg.pct_pt_jemaat if mcfg and mcfg.pct_pt_jemaat is not None else PCT_DEFAULTS_LIVE["pct_pt_jemaat"]),
        "pct_khusus_jemaat": float(mcfg.pct_khusus_jemaat if mcfg and mcfg.pct_khusus_jemaat is not None else PCT_DEFAULTS_LIVE["pct_khusus_jemaat"]),
        "pct_x_uni": float(ucfg.pct_x_uni if ucfg and ucfg.pct_x_uni is not None else 0.0),
        "pct_pt_uni": float(ucfg.pct_pt_uni if ucfg and ucfg.pct_pt_uni is not None else 0.0),
        "pct_khusus_uni": float(ucfg.pct_khusus_uni if ucfg and ucfg.pct_khusus_uni is not None else 0.0),
    }


def _compute_live_porsi(
    x: int, pt: int, kh: int, pct: dict,
) -> tuple[int, int, int, int, int, int]:
    """Hitung porsi LIVE per Jerry Model B (pct_uni applied to TOTAL).

    Returns (pm_x, pm_pt, pm_kh, pj_x, pj_pt, pj_kh).

    Formula:
      pj_x = round(x * pct_x_jemaat)
      pu_x = round(x * pct_x_uni)
      pm_x = x - pj_x - pu_x

    Layer 1 + Layer 2 — porsi_misi NET setelah Uni. Konsisten dengan
    compute_porsi() di porsi_calculator.py.
    """
    pj_x = int(round(x * pct["pct_x_jemaat"]))
    pj_pt = int(round(pt * pct["pct_pt_jemaat"]))
    pu_x = int(round(x * pct.get("pct_x_uni", 0.0) or 0.0))
    pu_pt = int(round(pt * pct.get("pct_pt_uni", 0.0) or 0.0))
    pm_x = max(0, x - pj_x - pu_x)
    pm_pt = max(0, pt - pj_pt - pu_pt)
    # KH: pct_khusus_jemaat = fraction to MISI (BUKAN to Jemaat).
    # Locked at 0 → 100% stays in Jemaat, 0% to Misi.
    pu_kh = int(round(kh * pct.get("pct_khusus_uni", 0.0) or 0.0))
    pm_kh = int(round(kh * pct["pct_khusus_jemaat"]))
    pj_kh = max(0, kh - pm_kh - pu_kh)
    return pm_x, pm_pt, pm_kh, pj_x, pj_pt, pj_kh


def _aggregate_by_minggu(
    rows: List[Kuitansi],
    tenants_map: dict,
    misi_cfg: dict,
    uni_cfg: dict,
    db: Session,
) -> List[MingguanItem]:
    """T47: Group rows by id_rekap_mingguan + hitung porsi LIVE (bukan stored).

    Sebelumnya pakai r.porsi_kantor_misi + r.porsi_kas_jemaat (stored dari
    approval). Sekarang recompute dari PersentaseConfig supaya agregat
    reactive terhadap slider changes.
    """
    grouped: dict[str, list] = {}  # S4-D.R1: type annotation for mypy
    for r in rows:
        if r.id_rekap_mingguan not in grouped:
            grouped[r.id_rekap_mingguan] = []
        grouped[r.id_rekap_mingguan].append(r)

    items = []
    for id_rekap, group in grouped.items():
        # Group by tenant_id within each minggu (pct berbeda per tenant)
        per_tenant_agg: dict[int, dict] = {}
        for r in group:
            tid = r.tenant_id
            if tid not in per_tenant_agg:
                per_tenant_agg[tid] = {"x": 0, "pt": 0, "kh": 0, "n": 0}
            per_tenant_agg[tid]["x"] += int(r.perpuluhan_x_angka or 0)
            per_tenant_agg[tid]["pt"] += int(r.pt_angka or 0)
            per_tenant_agg[tid]["kh"] += int(r.khusus_angka or 0)
            per_tenant_agg[tid]["n"] += 1

        sum_x = sum_pt = sum_kh = 0
        sum_pm = sum_pj = 0
        for tid, agg in per_tenant_agg.items():
            pct = _pct_for_tenant_id(tid, tenants_map, misi_cfg, uni_cfg, db)
            pm_x, pm_pt, pm_kh, pj_x, pj_pt, pj_kh = _compute_live_porsi(
                agg["x"], agg["pt"], agg["kh"], pct,
            )
            sum_x += agg["x"]
            sum_pt += agg["pt"]
            sum_kh += agg["kh"]
            sum_pm += pm_x + pm_pt + pm_kh
            sum_pj += pj_x + pj_pt + pj_kh

        items.append(MingguanItem(
            id_rekap_mingguan=id_rekap,
            tanggal_sabat=str(group[0].tanggal_sabat) if group[0].tanggal_sabat else "",
            jumlah_kuitansi=len(group),
            total_x=sum_x,
            total_pt=sum_pt,
            total_khusus=sum_kh,
            total_semua=sum_x + sum_pt + sum_kh,
            porsi_kantor_misi=sum_pm,
            porsi_kas_jemaat=sum_pj,
        ))

    # Sort by tanggal_sabat desc (minggu terbaru dulu)
    items.sort(key=lambda x: x.tanggal_sabat, reverse=True)
    return items


def _filter_by_bulan(rows: List[Kuitansi], bulan: Optional[str]) -> List[Kuitansi]:
    """Filter rows by bulan (YYYY-MM). Kalau None, return all."""
    if not bulan:
        return rows
    return [r for r in rows if r.tanggal_sabat and r.tanggal_sabat.startswith(bulan)]


# ===== GET /agregat/tenant =====

@router.get("/tenant", tags=['Agregat'], response_model=AgregatTenantOut)
def agregat_tenant(
    bulan: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Agregat per minggu untuk tenant caller.
    Dipakai oleh Pendeta/Ketua/Bendahara.
    """
    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id == tenant.id)
        .filter(Kuitansi.is_purged == False)
        .all()
    )
    rows = _filter_by_bulan(rows, bulan)

    # T47: pre-load pct contexts untuk live calculation
    tenants_map, misi_cfg, uni_cfg = _load_pct_contexts(db, [tenant.id])
    minggu_items = _aggregate_by_minggu(rows, tenants_map, misi_cfg, uni_cfg, db)

    grand_total_x = sum(m.total_x for m in minggu_items)
    grand_total_pt = sum(m.total_pt for m in minggu_items)
    grand_total_khusus = sum(m.total_khusus for m in minggu_items)
    grand_total_semua = grand_total_x + grand_total_pt + grand_total_khusus
    grand_total_porsi_misi = sum(m.porsi_kantor_misi for m in minggu_items)
    grand_total_porsi_jemaat = sum(m.porsi_kas_jemaat for m in minggu_items)

    return AgregatTenantOut(
        tenant_id=tenant.id,
        nama_jemaat=tenant.nama_jemaat_lokal,
        bulan=bulan,
        minggu_items=minggu_items,
        grand_total_x=grand_total_x,
        grand_total_pt=grand_total_pt,
        grand_total_khusus=grand_total_khusus,
        grand_total_semua=grand_total_semua,
        grand_total_porsi_misi=grand_total_porsi_misi,
        grand_total_porsi_jemaat=grand_total_porsi_jemaat,
        grand_total_huruf=bilang(grand_total_semua),
    )


# ===== GET /agregat/misi =====

@router.get("/misi", tags=['Agregat'], response_model=AgregatMisiOut)
def agregat_misi(
    bulan: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Agregat per minggu untuk SEMUA jemaat di misi caller (Auditor Misi).
    RBAC: AUDITOR_MISI only.
    """
    if current_user["role"] != "AUDITOR_MISI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Auditor Misi")

    caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not caller_tenant or not caller_tenant.misi_konferens_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Auditor belum terkait Misi")

    misi_id = caller_tenant.misi_konferens_id
    misi = db.query(MisiKonferens).filter(MisiKonferens.id == misi_id).first()
    if not misi:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Misi tidak ditemukan")

    # Semua jemaat di misi ini
    jemaat_tenants = (
        db.query(Tenant)
        .filter(Tenant.misi_konferens_id == misi_id)
        .all()
    )
    jemaat_ids = [t.id for t in jemaat_tenants]

    # Aggregate semua kuitansi
    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id.in_(jemaat_ids))
        .filter(Kuitansi.is_purged == False)
        .all()
    )
    rows = _filter_by_bulan(rows, bulan)

    # T47: pre-load pct contexts untuk live calculation
    tenants_map, misi_cfg, uni_cfg = _load_pct_contexts(db, jemaat_ids)
    minggu_items = _aggregate_by_minggu(rows, tenants_map, misi_cfg, uni_cfg, db)

    # Summary per jemaat — optimized: GROUP BY tenant_id (single query, no Python loop)
    agg_per_tenant = (
        db.query(
            Kuitansi.tenant_id,
            func.count(Kuitansi.id).label("jumlah"),
            func.coalesce(func.sum(Kuitansi.perpuluhan_x_angka), 0).label("total_x"),
            func.coalesce(func.sum(Kuitansi.pt_angka), 0).label("total_pt"),
            func.coalesce(func.sum(Kuitansi.khusus_angka), 0).label("total_khusus"),
            func.coalesce(func.sum(Kuitansi.porsi_kantor_misi), 0).label("porsi_misi"),
            func.coalesce(func.sum(Kuitansi.porsi_kas_jemaat), 0).label("porsi_jemaat"),
        )
        .filter(Kuitansi.tenant_id.in_(jemaat_ids))
        .filter(Kuitansi.is_purged == False)
        .group_by(Kuitansi.tenant_id)
        .all()
    )

    # Build map tenant_id → aggregate
    agg_map = {row.tenant_id: row for row in agg_per_tenant}

    # Apply bulan filter kalau ada
    if bulan:
        agg_per_tenant_bulan = (
            db.query(
                Kuitansi.tenant_id,
                func.count(Kuitansi.id).label("jumlah"),
                func.coalesce(func.sum(Kuitansi.perpuluhan_x_angka), 0).label("total_x"),
                func.coalesce(func.sum(Kuitansi.pt_angka), 0).label("total_pt"),
                func.coalesce(func.sum(Kuitansi.khusus_angka), 0).label("total_khusus"),
                func.coalesce(func.sum(Kuitansi.porsi_kantor_misi), 0).label("porsi_misi"),
                func.coalesce(func.sum(Kuitansi.porsi_kas_jemaat), 0).label("porsi_jemaat"),
            )
            .filter(Kuitansi.tenant_id.in_(jemaat_ids))
            .filter(Kuitansi.is_purged == False)
            .filter(Kuitansi.tanggal_sabat.like(f"{bulan}%"))
            .group_by(Kuitansi.tenant_id)
            .all()
        )
        agg_map = {row.tenant_id: row for row in agg_per_tenant_bulan}

    jemaat_summary = []
    for t in jemaat_tenants:
        agg = agg_map.get(t.id)
        jemaat_summary.append(JemaatSummary(
            tenant_id=t.id,
            nama_jemaat=t.nama_jemaat_lokal,
            nama_pendeta=t.nama_pendeta,
            nama_ketua_keuangan=t.nama_ketua_keuangan,
            nama_bendahara=t.nama_bendahara,
            jumlah_kuitansi=agg.jumlah if agg else 0,
            total_x=agg.total_x if agg else 0,
            total_pt=agg.total_pt if agg else 0,
            total_khusus=agg.total_khusus if agg else 0,
            total_porsi_misi=agg.porsi_misi if agg else 0,
            total_porsi_jemaat=agg.porsi_jemaat if agg else 0,
        ))

    # Sort jemaat by total_semua desc
    jemaat_summary.sort(
        key=lambda j: j.total_x + j.total_pt + j.total_khusus,
        reverse=True,
    )

    grand_total_x = sum(m.total_x for m in minggu_items)
    grand_total_pt = sum(m.total_pt for m in minggu_items)
    grand_total_khusus = sum(m.total_khusus for m in minggu_items)
    grand_total_semua = grand_total_x + grand_total_pt + grand_total_khusus
    grand_total_porsi_misi = sum(m.porsi_kantor_misi for m in minggu_items)
    grand_total_porsi_jemaat = sum(m.porsi_kas_jemaat for m in minggu_items)

    return AgregatMisiOut(
        misi_id=misi_id,
        nama_misi=misi.nama_resmi,
        bulan=bulan,
        minggu_items=minggu_items,
        grand_total=grand_total_semua,
        grand_total_x=grand_total_x,
        grand_total_pt=grand_total_pt,
        grand_total_khusus=grand_total_khusus,
        grand_total_porsi_misi=grand_total_porsi_misi,
        grand_total_porsi_jemaat=grand_total_porsi_jemaat,
        grand_total_huruf=terbilang(grand_total_semua),
        jemaat_count=len(jemaat_tenants),
        jemaat_summary=jemaat_summary,
    )


# ===== GET /agregat/uni =====

@router.get("/uni", tags=['Agregat'], response_model=AgregatMisiOut)
def agregat_uni(
    bulan: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Agregat per minggu untuk SEMUA misi di uni caller (Admin Uni).
    RBAC: ADMIN_UNI only.

    Notes: Misi ditampilkan sebagai 'jemaat' di struktur ini.
    """
    if current_user["role"] != "ADMIN_UNI":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Admin Uni")

    caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not caller_tenant or not caller_tenant.nama_uni:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admin belum terkait Uni")

    uni = db.query(Uni).filter(Uni.nama_resmi == caller_tenant.nama_uni).first()
    if not uni:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uni tidak ditemukan")

    # Semua misi di uni ini
    misi_list = (
        db.query(MisiKonferens)
        .filter(MisiKonferens.uni_id == uni.id)
        .all()
    )

    # Semua tenant (misi) di uni ini
    misi_tenants = (
        db.query(Tenant)
        .filter(Tenant.misi_konferens_id.in_([m.id for m in misi_list]))
        .all()
    )
    tenant_ids = [t.id for t in misi_tenants]

    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id.in_(tenant_ids))
        .filter(Kuitansi.is_purged == False)
        .all()
    )
    rows = _filter_by_bulan(rows, bulan)

    # T47: pre-load pct contexts untuk live calculation
    tenants_map, misi_cfg, uni_cfg = _load_pct_contexts(db, tenant_ids)
    minggu_items = _aggregate_by_minggu(rows, tenants_map, misi_cfg, uni_cfg, db)

    # Per-misi summary optimized: single GROUP BY query (bukan Python loop)
    agg_per_tenant = (
        db.query(
            Kuitansi.tenant_id,
            func.count(Kuitansi.id).label("jumlah"),
            func.coalesce(func.sum(Kuitansi.perpuluhan_x_angka), 0).label("total_x"),
            func.coalesce(func.sum(Kuitansi.pt_angka), 0).label("total_pt"),
            func.coalesce(func.sum(Kuitansi.khusus_angka), 0).label("total_khusus"),
            func.coalesce(func.sum(Kuitansi.porsi_kantor_misi), 0).label("porsi_misi"),
            func.coalesce(func.sum(Kuitansi.porsi_kas_jemaat), 0).label("porsi_jemaat"),
        )
        .filter(Kuitansi.tenant_id.in_(tenant_ids))
        .filter(Kuitansi.is_purged == False)
        .filter(Kuitansi.tanggal_sabat.like(f"{bulan}%") if bulan else True)
        .group_by(Kuitansi.tenant_id)
        .all()
    )
    agg_map = {row.tenant_id: row for row in agg_per_tenant}

    misi_summary = []
    for t in misi_tenants:
        agg = agg_map.get(t.id)
        misi_summary.append(JemaatSummary(
            tenant_id=t.id,
            nama_jemaat=t.nama_jemaat_lokal,
            nama_pendeta=t.nama_pendeta,
            nama_ketua_keuangan=t.nama_ketua_keuangan,
            nama_bendahara=t.nama_bendahara,
            jumlah_kuitansi=agg.jumlah if agg else 0,
            total_x=agg.total_x if agg else 0,
            total_pt=agg.total_pt if agg else 0,
            total_khusus=agg.total_khusus if agg else 0,
            total_porsi_misi=agg.porsi_misi if agg else 0,
            total_porsi_jemaat=agg.porsi_jemaat if agg else 0,
        ))

    misi_summary.sort(
        key=lambda m: m.total_x + m.total_pt + m.total_khusus,
        reverse=True,
    )

    grand_total_x = sum(m.total_x for m in minggu_items)
    grand_total_pt = sum(m.total_pt for m in minggu_items)
    grand_total_khusus = sum(m.total_khusus for m in minggu_items)
    grand_total_semua = grand_total_x + grand_total_pt + grand_total_khusus
    grand_total_porsi_misi = sum(m.porsi_kantor_misi for m in minggu_items)
    grand_total_porsi_jemaat = sum(m.porsi_kas_jemaat for m in minggu_items)

    return AgregatMisiOut(
        misi_id=None,
        nama_misi=uni.nama_resmi,
        bulan=bulan,
        minggu_items=minggu_items,
        grand_total=grand_total_semua,
        grand_total_x=grand_total_x,
        grand_total_pt=grand_total_pt,
        grand_total_khusus=grand_total_khusus,
        grand_total_porsi_misi=grand_total_porsi_misi,
        grand_total_porsi_jemaat=grand_total_porsi_jemaat,
        grand_total_huruf=terbilang(grand_total_semua),
        jemaat_count=len(misi_tenants),
        jemaat_summary=misi_summary,
    )

# ===== T34: Chart data endpoint =====

class ChartMingguanItem(BaseModel):
    tanggal_sabat: str
    label: str  # "15 Ags" (short label for x-axis)
    x: int
    pt: int
    khusus: int
    total: int


class ChartMingguanOut(BaseModel):
    scope: str  # "tenant" | "misi" | "uni"
    n_weeks: int
    items: List[ChartMingguanItem]
    total_x: int
    total_pt: int
    total_khusus: int
    total_all: int


def _short_label(tgl: str) -> str:
    """Format '2026-08-15' → '15 Ags'."""
    bulan_singkat = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
        7: "Jul", 8: "Ags", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
    }
    try:
        y, m, d = tgl.split("-")
        return f"{int(d)} {bulan_singkat[int(m)]}"
    except Exception:
        return tgl


def _build_chart_for_tenant_ids(db: Session, tenant_ids: List[int], n_weeks: int) -> List[ChartMingguanItem]:
    """Bangun list ChartMingguanItem untuk kumpulan tenant (1+, sesuai scope)."""
    if not tenant_ids:
        return []
    # Get distinct (tanggal_sabat) terakhir, lalu agregat per sabat
    rows = (
        db.query(
            Kuitansi.tanggal_sabat,
            func.sum(Kuitansi.perpuluhan_x_angka).label("sum_x"),
            func.sum(Kuitansi.pt_angka).label("sum_pt"),
            func.sum(Kuitansi.khusus_angka).label("sum_kh"),
            func.count(Kuitansi.id).label("n"),
        )
        .filter(Kuitansi.tenant_id.in_(tenant_ids))
        .filter(Kuitansi.is_purged == False)  # noqa: E712
        .filter(Kuitansi.status == "finalized")
        .group_by(Kuitansi.tanggal_sabat)
        .order_by(Kuitansi.tanggal_sabat.desc())
        .limit(n_weeks)
        .all()
    )
    items: List[ChartMingguanItem] = []
    for r in reversed(rows):  # chronological order
        sum_x = int(r.sum_x or 0)
        sum_pt = int(r.sum_pt or 0)
        sum_kh = int(r.sum_kh or 0)
        items.append(ChartMingguanItem(
            tanggal_sabat=r.tanggal_sabat,
            label=_short_label(r.tanggal_sabat),
            x=sum_x,
            pt=sum_pt,
            khusus=sum_kh,
            total=sum_x + sum_pt + sum_kh,
        ))
    return items


# ===== T36 Redesign: Sabat-ini (current sabat table) + YTD cumulative =====

class SabatIniItem(BaseModel):
    """Baris tabel 'Persembahan sabat ini' (1 sabat saja, sabat berjalan).

    T40: pakai kalkulasi LIVE dari PersentaseConfig (bukan stored porsi_kantor_misi).
    Bendahara sekarang melihat porsi_uni (Layer 2) + breakdown khusus (KH).
    """
    no: int
    id_kuitansi: int
    nomor_kuitansi: str
    nama_pemberi: Optional[str] = None
    tanggal_sabat: str
    perpuluhan_x_angka: int
    pt_angka: int
    khusus_angka: int
    total: int
    porsi_misi_x: int
    porsi_misi_pt: int
    porsi_misi_kh: int
    porsi_uni_x: int = 0
    porsi_uni_pt: int = 0
    porsi_uni_kh: int = 0
    porsi_jemaat_x: int
    porsi_jemaat_pt: int
    porsi_jemaat_kh: int
    id_rekap_mingguan: str


class SabatIniRow(BaseModel):
    """1 baris agregat: total per tenant/jemaat/misi (untuk Auditor/Admin).

    T40: pakai kalkulasi LIVE dari PersentaseConfig. Porsi_jemaat dipecah
    per-bagian (X/PT/KH) supaya transfer bank nanti bisa presisi.
    """
    no: int
    entity_id: int
    entity_name: str
    jumlah_kuitansi: int
    total_x: int
    total_pt: int
    total_khusus: int
    total_semua: int
    porsi_uni_x: int = 0
    porsi_uni_pt: int = 0
    porsi_uni_kh: int = 0
    porsi_misi_x: int = 0
    porsi_misi_pt: int = 0
    porsi_misi_kh: int = 0
    porsi_jemaat_x: int = 0
    porsi_jemaat_pt: int = 0
    porsi_jemaat_kh: int = 0


class SabatIniOut(BaseModel):
    """Response untuk Tabel 'Persembahan sabat ini'."""
    scope: str  # 'tenant' | 'misi' | 'uni'
    sabat_ke: int
    tanggal_sabat: str
    hari: str
    bulan_nama: str
    tahun: int
    # Rows table (1 row per kuitansi untuk tenant; 1 row per jemaat/misi untuk auditor/admin)
    items: List[dict]
    grand_total_x: int
    grand_total_pt: int
    grand_total_khusus: int
    grand_total_semua: int
    grand_total_porsi_misi_x: int
    grand_total_porsi_misi_pt: int
    grand_total_porsi_misi_kh: int = 0
    grand_total_porsi_uni_x: int = 0
    grand_total_porsi_uni_pt: int = 0
    grand_total_porsi_uni_kh: int = 0
    grand_total_porsi_jemaat: int = 0      # total gabung X+PT+KH (back-compat)
    grand_total_porsi_jemaat_x: int = 0
    grand_total_porsi_jemaat_pt: int = 0
    grand_total_porsi_jemaat_kh: int = 0
    grand_total_huruf: str


class YtdBarOut(BaseModel):
    """6 angka kumulatif YTD untuk grafik batang."""
    scope: str
    tahun: int
    sabat_ke: int  # sabat berjalan
    total_perpuluhan: int          # bar 1: total X sejak 1 Jan tahun ini
    total_persembahan_terpadu: int  # bar 2: total PT sejak 1 Jan tahun ini
    total_persembahan_khusus: int  # bar 3: total Khusus sejak 1 Jan tahun ini
    total_porsi_misi_x: int        # bar 4: porsi X yang di setor ke Misi
    total_porsi_misi_pt: int       # bar 5: porsi PT yang di setor ke Misi
    total_porsi_jemaat: int        # bar 6: porsi Jemaat (X + PT)


def _tenant_ids_for_caller(db: Session, current_user: dict) -> tuple[List[int], str]:
    """Return (tenant_ids_in_scope, scope_label) sesuai role caller.

    FASE4-S5C: Sekarang menjadi thin wrapper di atas resolve_tenant_scope
    (single source of truth). Tetap return (ids, label) tuple untuk
    backward-compat dengan kode agregat.py yang consume (ids, label).
    """
    scope = resolve_tenant_scope(db, current_user)
    if not scope.visible_tenant_ids:
        # Caller tidak punya akses apapun — surface error biar caller tau
        # ada misconfiguration (tenant record hilang atau role belum di-link).
        if scope.role in ("AUDITOR_MISI",):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Caller belum terkait misi/konferens",
            )
        if scope.role == "ADMIN_UNI":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Caller belum terkait uni",
            )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Tenant caller tidak ditemukan",
        )
    # Map role → scope_label untuk downstream consumer
    label_map = {
        "BENDAHARA": "tenant",
        "KETUA_KEUANGAN": "tenant",
        "PENDETA": "tenant",
        "AUDITOR_MISI": "misi",
        "ADMIN_UNI": "uni",
    }
    label = label_map.get(scope.role, "unknown")
    return scope.visible_tenant_ids, label


@router.get("/sabat-ini", tags=['Agregat'], response_model=SabatIniOut)
def agregat_sabat_ini(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Tabel 'Persembahan sabat ini' — data HANYA untuk sabat berjalan.

    Untuk tenant caller (Pendeta/Ketua/Bendahara): 1 row per kuitansi, dengan
    nama_pemberi.

    Untuk auditor/admin: 1 row per jemaat/misi (agregat), tanpa nama perorangan.
    """
    info = get_current_sabat()
    tanggal_sabat = info["tanggal_sabat"]
    sabat_ke = info["sabat_ke"]
    tahun = info["tahun"]

    bulan_nama_id = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember",
    }

    tenant_ids, scope = _tenant_ids_for_caller(db, current_user)
    role = current_user["role"]

    # Base query: kuitansi di sabat ini
    base_q = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id.in_(tenant_ids))
        .filter(Kuitansi.tanggal_sabat == tanggal_sabat)
        .filter(Kuitansi.is_purged == False)  # noqa: E712
    )

    items: List[dict] = []
    sum_x = sum_pt = sum_kh = 0
    sum_misi_x = sum_misi_pt = sum_misi_kh = 0
    sum_uni_x = sum_uni_pt = sum_uni_kh = 0
    sum_jemaat_x = sum_jemaat_pt = sum_jemaat_kh = 0

    # T40: Resolve PersentaseConfig dari caller's tenant (untuk scope tenant)
    # atau per-entity (untuk scope misi/uni). Pakai default yang aman kalau
    # config belum di-set.
    PCT_DEFAULTS = {
        "pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.5,
        "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0,
    }

    def _resolve_pct_for_misi(misi_id: int) -> dict:
        cfg = (
            db.query(PersentaseConfig)
            .filter(PersentaseConfig.scope == "MISI", PersentaseConfig.ref_id == misi_id)
            .first()
        )
        if not cfg:
            return {**PCT_DEFAULTS}
        return {
            "pct_x_jemaat": float(cfg.pct_x_jemaat if cfg.pct_x_jemaat is not None else PCT_DEFAULTS["pct_x_jemaat"]),
            "pct_pt_jemaat": float(cfg.pct_pt_jemaat if cfg.pct_pt_jemaat is not None else PCT_DEFAULTS["pct_pt_jemaat"]),
            "pct_khusus_jemaat": float(cfg.pct_khusus_jemaat if cfg.pct_khusus_jemaat is not None else PCT_DEFAULTS["pct_khusus_jemaat"]),
            "pct_x_uni": PCT_DEFAULTS["pct_x_uni"],
            "pct_pt_uni": PCT_DEFAULTS["pct_pt_uni"],
            "pct_khusus_uni": PCT_DEFAULTS["pct_khusus_uni"],
        }

    def _resolve_pct_for_uni(uni_id: int) -> dict:
        """Untuk Layer 2: uni-scoped pct (ditetapkan Admin Uni)."""
        cfg = (
            db.query(PersentaseConfig)
            .filter(PersentaseConfig.scope == "UNI", PersentaseConfig.ref_id == uni_id)
            .first()
        )
        if not cfg:
            return {"pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0}
        return {
            "pct_x_uni": float(cfg.pct_x_uni or 0.0),
            "pct_pt_uni": float(cfg.pct_pt_uni or 0.0),
            "pct_khusus_uni": float(cfg.pct_khusus_uni or 0.0),
        }

    # Untuk scope tenant: resolve 1× saja (1 tenant → 1 misi → 1 uni)
    tenant_pct: Optional[dict] = None
    if scope == "tenant":
        caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
        if caller_tenant and caller_tenant.misi_konferens_id:
            tenant_pct = _resolve_pct_for_misi(caller_tenant.misi_konferens_id)
            misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == caller_tenant.misi_konferens_id).first()
            if misi_row:
                uni_pct = _resolve_pct_for_uni(misi_row.uni_id)
                tenant_pct.update(uni_pct)
        else:
            tenant_pct = {**PCT_DEFAULTS}
        assert tenant_pct is not None  # S4-D.R1: narrow Optional[dict] for mypy

    if scope == "tenant":
        # Bendahara/Pendeta/Ketua: tampilkan per-kuitansi dengan nama_pemberi
        rows = base_q.filter(Kuitansi.status == "finalized").order_by(Kuitansi.nomor_kuitansi.asc()).all()
        for i, r in enumerate(rows, start=1):
            x = int(r.perpuluhan_x_angka or 0)
            pt = int(r.pt_angka or 0)
            kh = int(r.khusus_angka or 0)
            # T81 (revisi 2026-08-23): Jerry Model B (hierarchical) —
            # porsi_uni adalah fraction of (1 - pct_jemaat), bukan of total.
            # pct_pt_jemaat = porsi JEMAAT langsung, pct_pt_uni = porsi UNI dari sisa.
            from app.utils.porsi_calculator import compute_porsi
            p = compute_porsi(
                x=x, pt=pt, kh=kh,
                pct_x_jemaat=tenant_pct["pct_x_jemaat"],
                pct_pt_jemaat=tenant_pct["pct_pt_jemaat"],
                pct_khusus_jemaat=tenant_pct["pct_khusus_jemaat"],
                pct_x_uni=tenant_pct.get("pct_x_uni", 0.0),
                pct_pt_uni=tenant_pct.get("pct_pt_uni", 0.0),
                pct_khusus_uni=tenant_pct.get("pct_khusus_uni", 0.0),
            )
            pm_x, pm_pt, pm_kh = p["pm_x"], p["pm_pt"], p["pm_kh"]
            pu_x, pu_pt, pu_kh = p["pu_x"], p["pu_pt"], p["pu_kh"]
            pj_x, pj_pt, pj_kh = p["pj_x"], p["pj_pt"], p["pj_kh"]
            items.append({
                "no": i,
                "id_kuitansi": r.id,
                "nomor_kuitansi": r.nomor_kuitansi,
                "nama_pemberi": decrypt_pii(r.nama_umat_encrypted) if r.nama_umat_encrypted else None,
                "tanggal_sabat": r.tanggal_sabat,
                "perpuluhan_x_angka": x,
                "pt_angka": pt,
                "khusus_angka": kh,
                "total": x + pt + kh,
                "porsi_misi_x": pm_x,
                "porsi_misi_pt": pm_pt,
                "porsi_misi_kh": pm_kh,
                "porsi_uni_x": pu_x,
                "porsi_uni_pt": pu_pt,
                "porsi_uni_kh": pu_kh,
                "porsi_jemaat_x": pj_x,
                "porsi_jemaat_pt": pj_pt,
                "porsi_jemaat_kh": pj_kh,
                "id_rekap_mingguan": r.id_rekap_mingguan,
            })
            sum_x += x
            sum_pt += pt
            sum_kh += kh
            sum_misi_x += pm_x
            sum_misi_pt += pm_pt
            sum_misi_kh += pm_kh
            sum_uni_x += pu_x
            sum_uni_pt += pu_pt
            sum_uni_kh += pu_kh
            sum_jemaat_x += pj_x
            sum_jemaat_pt += pj_pt
            sum_jemaat_kh += pj_kh
    else:
        # Auditor/Admin: 1 row per jemaat/misi (agregat, TANPA nama perorangan)
        from sqlalchemy import func as sql_func
        agg_per_tenant = (
            db.query(
                Kuitansi.tenant_id,
                sql_func.count(Kuitansi.id).label("n"),
                sql_func.coalesce(sql_func.sum(Kuitansi.perpuluhan_x_angka), 0).label("x"),
                sql_func.coalesce(sql_func.sum(Kuitansi.pt_angka), 0).label("pt"),
                sql_func.coalesce(sql_func.sum(Kuitansi.khusus_angka), 0).label("kh"),
            )
            .filter(Kuitansi.tenant_id.in_(tenant_ids))
            .filter(Kuitansi.tanggal_sabat == tanggal_sabat)
            .filter(Kuitansi.is_purged == False)  # noqa: E712
            .filter(Kuitansi.status == "finalized")
            .group_by(Kuitansi.tenant_id)
            .all()
        )

        tenants_map = {t.id: t for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}

        # T40 LIVE: pre-resolve PersentaseConfig per entity.
        # Auditor Misi: semua entity (jemaat) dalam misi caller → share 1 set MISI pct
        # Admin Uni: semua entity (misi) dalam uni caller → tiap misi punya MISI pct sendiri,
        # tapi UNI pct sama untuk seluruh uni
        entity_pcts: dict[int, dict] = {}  # entity_id (tenant_id) → pct dict
        unique_uni_ids: set[int] = set()
        for tid in tenants_map.keys():
            t = tenants_map[tid]
            if t.misi_konferens_id:
                pct = _resolve_pct_for_misi(t.misi_konferens_id)
                entity_pcts[tid] = pct
                misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == t.misi_konferens_id).first()
                if misi_row:
                    unique_uni_ids.add(misi_row.uni_id)
        uni_pcts_map: dict[int, dict] = {
            uid: _resolve_pct_for_uni(uid) for uid in unique_uni_ids
        }

        # Sort entity: descending total persembahan (auditor/admin ingin lihat jemaat/misi terbesar dulu)
        for i, a in enumerate(sorted(agg_per_tenant, key=lambda r: -(int(r.x) + int(r.pt) + int(r.kh))), start=1):
            t = tenants_map.get(a.tenant_id)
            name = t.nama_jemaat_lokal if t else f"Tenant {a.tenant_id}"
            total_x = int(a.x)
            total_pt = int(a.pt)
            total_kh = int(a.kh)
            total_semua = total_x + total_pt + total_kh

            pct = entity_pcts.get(a.tenant_id, PCT_DEFAULTS)
            uni_pct = {"pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0}
            if t and t.misi_konferens_id:
                misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == t.misi_konferens_id).first()
                if misi_row and misi_row.uni_id in uni_pcts_map:
                    uni_pct = uni_pcts_map[misi_row.uni_id]
            # T81 (revisi 2026-08-23): Jerry Model B (hierarchical).
            from app.utils.porsi_calculator import compute_porsi
            p = compute_porsi(
                x=total_x, pt=total_pt, kh=total_kh,
                pct_x_jemaat=pct["pct_x_jemaat"],
                pct_pt_jemaat=pct["pct_pt_jemaat"],
                pct_khusus_jemaat=pct["pct_khusus_jemaat"],
                pct_x_uni=uni_pct["pct_x_uni"],
                pct_pt_uni=uni_pct["pct_pt_uni"],
                pct_khusus_uni=uni_pct["pct_khusus_uni"],
            )
            pm_x, pm_pt, pm_kh = p["pm_x"], p["pm_pt"], p["pm_kh"]
            pu_x, pu_pt, pu_kh = p["pu_x"], p["pu_pt"], p["pu_kh"]
            pj_x, pj_pt, pj_kh = p["pj_x"], p["pj_pt"], p["pj_kh"]

            items.append({
                "no": i,
                "entity_id": a.tenant_id,
                "entity_name": name,
                "jumlah_kuitansi": int(a.n),
                "total_x": total_x,
                "total_pt": total_pt,
                "total_khusus": total_kh,
                "total_semua": total_semua,
                "porsi_uni_x": pu_x,
                "porsi_uni_pt": pu_pt,
                "porsi_uni_kh": pu_kh,
                "porsi_misi_x": pm_x,
                "porsi_misi_pt": pm_pt,
                "porsi_misi_kh": pm_kh,
                "porsi_jemaat_x": pj_x,
                "porsi_jemaat_pt": pj_pt,
                "porsi_jemaat_kh": pj_kh,
            })
            sum_x += total_x
            sum_pt += total_pt
            sum_kh += total_kh
            sum_misi_x += pm_x
            sum_misi_pt += pm_pt
            sum_misi_kh += pm_kh
            sum_uni_x += pu_x
            sum_uni_pt += pu_pt
            sum_uni_kh += pu_kh
            sum_jemaat_x += pj_x
            sum_jemaat_pt += pj_pt
            sum_jemaat_kh += pj_kh

    # Parse tanggal_sabat untuk bulan_nama
    from datetime import datetime as dt_cls
    try:
        tgl_obj = dt_cls.fromisoformat(tanggal_sabat)
        bulan_nama = bulan_nama_id[tgl_obj.month]
    except Exception:
        bulan_nama = ""

    return SabatIniOut(
        scope=scope,
        sabat_ke=sabat_ke,
        tanggal_sabat=tanggal_sabat,
        hari=info["hari"],
        bulan_nama=bulan_nama,
        tahun=tahun,
        items=items,
        grand_total_x=sum_x,
        grand_total_pt=sum_pt,
        grand_total_khusus=sum_kh,
        grand_total_semua=sum_x + sum_pt + sum_kh,
        grand_total_porsi_misi_x=sum_misi_x,
        grand_total_porsi_misi_pt=sum_misi_pt,
        grand_total_porsi_misi_kh=sum_misi_kh,
        grand_total_porsi_uni_x=sum_uni_x,
        grand_total_porsi_uni_pt=sum_uni_pt,
        grand_total_porsi_uni_kh=sum_uni_kh,
        grand_total_porsi_jemaat=sum_jemaat_x + sum_jemaat_pt + sum_jemaat_kh,
        grand_total_porsi_jemaat_x=sum_jemaat_x,
        grand_total_porsi_jemaat_pt=sum_jemaat_pt,
        grand_total_porsi_jemaat_kh=sum_jemaat_kh,
        grand_total_huruf=bilang(sum_x + sum_pt + sum_kh),
    )


@router.get("/ytd", tags=['Agregat'], response_model=YtdBarOut)
def agregat_ytd(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    6 angka kumulatif YTD (Year-To-Date) untuk grafik batang.

    Dihitung dari 1 Januari tahun ini sampai sabat berjalan.

    T47 hardening: porsi dihitung LIVE dari PersentaseConfig sekarang
    (seperti T40 untuk sabat-ini). Tidak pakai stored value agar grafik
    YTD reactive terhadap perubahan slider persentase.

    Returns 6 values:
    1. Total Perpuluhan (X) — sabat 1 tahun ini → sekarang
    2. Total Persembahan Terpadu (PT)
    3. Total Persembahan Khusus
    4. Total Porsi Misi X (X yang di setor ke Misi)
    5. Total Porsi Misi PT (PT yang di setor ke Misi)
    6. Total Porsi Jemaat (X + PT yang留在 jemaat)
    """
    info = get_current_sabat()
    tahun = info["tahun"]
    sabat_ke = info["sabat_ke"]
    tanggal_sabat = info["tanggal_sabat"]

    tenant_ids, scope = _tenant_ids_for_caller(db, current_user)
    if not tenant_ids:
        # No tenants in scope — return zeros
        return YtdBarOut(
            scope=scope, tahun=tahun, sabat_ke=sabat_ke,
            total_perpuluhan=0, total_persembahan_terpadu=0,
            total_persembahan_khusus=0, total_porsi_misi_x=0,
            total_porsi_misi_pt=0, total_porsi_jemaat=0,
        )

    # YTD = dari 1 Jan tahun ini sampai tanggal_sabat (inclusive)
    year_start = f"{tahun}-01-01"

    from sqlalchemy import func as sql_func
    # T47: Aggregate RAW values (X, PT, KH) per tenant (bukan pakai stored porsi).
    # Porsi akan dihitung LIVE di Python dari PersentaseConfig.
    agg_per_tenant = (
        db.query(
            Kuitansi.tenant_id,
            sql_func.coalesce(sql_func.sum(Kuitansi.perpuluhan_x_angka), 0).label("x"),
            sql_func.coalesce(sql_func.sum(Kuitansi.pt_angka), 0).label("pt"),
            sql_func.coalesce(sql_func.sum(Kuitansi.khusus_angka), 0).label("kh"),
        )
        .filter(Kuitansi.tenant_id.in_(tenant_ids))
        .filter(Kuitansi.tanggal_sabat >= year_start)
        .filter(Kuitansi.tanggal_sabat <= tanggal_sabat)
        .filter(Kuitansi.is_purged == False)  # noqa: E712
        .filter(Kuitansi.status == "finalized")
        .group_by(Kuitansi.tenant_id)
        .all()
    )

    # T47: Pre-resolve tenants + pct configs.
    PCT_DEFAULTS = {
        "pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.5,
        "pct_x_uni": 0.0, "pct_pt_uni": 0.0, "pct_khusus_uni": 0.0,
    }

    tenants_map = {t.id: t for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}

    # Collect unique misi_id dan uni_id
    unique_misi_ids: set[int] = set()
    unique_uni_ids: set[int] = set()
    for tid in tenants_map.keys():
        t = tenants_map[tid]
        if t.misi_konferens_id:
            unique_misi_ids.add(t.misi_konferens_id)
    if unique_misi_ids:
        misi_rows = db.query(MisiKonferens).filter(MisiKonferens.id.in_(unique_misi_ids)).all()
        for m in misi_rows:
            if m.uni_id:
                unique_uni_ids.add(m.uni_id)

    # Pre-load PersentaseConfig untuk setiap misi (scope=MISI) dan uni (scope=UNI)
    misi_cfg = {
        c.ref_id: c for c in db.query(PersentaseConfig).filter(
            PersentaseConfig.scope == "MISI",
            PersentaseConfig.ref_id.in_(unique_misi_ids) if unique_misi_ids else [0],
        ).all()
    }
    uni_cfg = {
        c.ref_id: c for c in db.query(PersentaseConfig).filter(
            PersentaseConfig.scope == "UNI",
            PersentaseConfig.ref_id.in_(unique_uni_ids) if unique_uni_ids else [0],
        ).all()
    }

    def _pct_for_tenant(tid: int) -> dict:
        t = tenants_map.get(tid)
        if not t or not t.misi_konferens_id:
            return {**PCT_DEFAULTS}
        mcfg = misi_cfg.get(t.misi_konferens_id)
        # UNI pct dari uni entity ini (resolve via misi → uni_id)
        misi_row = db.query(MisiKonferens).filter(MisiKonferens.id == t.misi_konferens_id).first()
        ucfg = uni_cfg.get(misi_row.uni_id) if misi_row else None
        return {
            "pct_x_jemaat": float(mcfg.pct_x_jemaat if mcfg and mcfg.pct_x_jemaat is not None else PCT_DEFAULTS["pct_x_jemaat"]),
            "pct_pt_jemaat": float(mcfg.pct_pt_jemaat if mcfg and mcfg.pct_pt_jemaat is not None else PCT_DEFAULTS["pct_pt_jemaat"]),
            "pct_khusus_jemaat": float(mcfg.pct_khusus_jemaat if mcfg and mcfg.pct_khusus_jemaat is not None else PCT_DEFAULTS["pct_khusus_jemaat"]),
            "pct_x_uni": float(ucfg.pct_x_uni if ucfg and ucfg.pct_x_uni is not None else 0.0),
            "pct_pt_uni": float(ucfg.pct_pt_uni if ucfg and ucfg.pct_pt_uni is not None else 0.0),
            "pct_khusus_uni": float(ucfg.pct_khusus_uni if ucfg and ucfg.pct_khusus_uni is not None else 0.0),
        }

    # T47: Hitung porsi LIVE per tenant, lalu aggregate grand total
    total_x = total_pt = total_kh = 0
    sum_misi_x = sum_misi_pt = sum_misi_kh = 0
    sum_jemaat_x = sum_jemaat_pt = sum_jemaat_kh = 0
    sum_uni_x = sum_uni_pt = sum_uni_kh = 0

    for a in agg_per_tenant:
        tid = a.tenant_id
        x = int(a.x or 0)
        pt = int(a.pt or 0)
        kh = int(a.kh or 0)
        pct = _pct_for_tenant(tid)

        # 2026-08-23: Jerry Model B — pct_uni applied to TOTAL
        pj_x = int(round(x * pct["pct_x_jemaat"]))
        pj_pt = int(round(pt * pct["pct_pt_jemaat"]))
        pu_x = int(round(x * pct["pct_x_uni"]))
        pu_pt = int(round(pt * pct["pct_pt_uni"]))
        pm_x = max(0, x - pj_x - pu_x)
        pm_pt = max(0, pt - pj_pt - pu_pt)
        # KH: pct_khusus_jemaat = fraction to MISI (semantik terbalik dari X/PT)
        pu_kh = int(round(kh * pct["pct_khusus_uni"]))
        pm_kh = int(round(kh * pct["pct_khusus_jemaat"]))
        pj_kh = max(0, kh - pm_kh - pu_kh)

        total_x += x
        total_pt += pt
        total_kh += kh
        sum_misi_x += pm_x
        sum_misi_pt += pm_pt
        sum_misi_kh += pm_kh
        sum_jemaat_x += pj_x
        sum_jemaat_pt += pj_pt
        sum_jemaat_kh += pj_kh
        sum_uni_x += pu_x
        sum_uni_pt += pu_pt
        sum_uni_kh += pu_kh

    # YTD bar uses total Porsi Misi (gabungan X + PT) + KH Misi (Layer 1 only, KH punya logic sendiri)
    # Untuk YtdBarOut: total_porsi_misi_x/pm_pt = langsung dari live calc
    return YtdBarOut(
        scope=scope,
        tahun=tahun,
        sabat_ke=sabat_ke,
        total_perpuluhan=total_x,
        total_persembahan_terpadu=total_pt,
        total_persembahan_khusus=total_kh,
        total_porsi_misi_x=sum_misi_x,
        total_porsi_misi_pt=sum_misi_pt,
        total_porsi_jemaat=sum_jemaat_x + sum_jemaat_pt,  # X+PT saja (sesuai definisi YtdBarOut)
    )


@router.get("/chart/mingguan", tags=['Agregat'], response_model=ChartMingguanOut)
def chart_mingguan(
    n_weeks: int = 8,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    T34: Chart data perpuluhan 8 minggu terakhir.

    Scope:
    - BENDAHARA/KETUA_KEUANGAN/PENDETA: tenant caller
    - AUDITOR_MISI: semua jemaat di misi caller
    - ADMIN_UNI: semua jemaat di uni caller
    """
    if n_weeks < 1 or n_weeks > 52:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "n_weeks harus 1-52")

    role = current_user["role"]
    tenant_id = current_user["tenant_id"]
    caller = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not caller:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant caller tidak ditemukan")

    if role in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA"):
        scope = "tenant"
        tenant_ids = [tenant_id]
    elif role == "AUDITOR_MISI":
        scope = "misi"
        if not caller.misi_konferens_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait misi")
        tenant_ids = [t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id == caller.misi_konferens_id).all()]
    elif role == "ADMIN_UNI":
        scope = "uni"
        if not caller.nama_uni:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Caller belum terkait uni")
        tenant_ids = [t.id for t in db.query(Tenant).filter(Tenant.nama_uni == caller.nama_uni).all()]
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role tidak dikenal")

    items = _build_chart_for_tenant_ids(db, tenant_ids, n_weeks)
    total_x = sum(i.x for i in items)
    total_pt = sum(i.pt for i in items)
    total_kh = sum(i.khusus for i in items)

    return ChartMingguanOut(
        scope=scope,
        n_weeks=n_weeks,
        items=items,
        total_x=total_x,
        total_pt=total_pt,
        total_khusus=total_kh,
        total_all=total_x + total_pt + total_kh,
    )
