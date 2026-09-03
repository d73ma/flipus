"""
FLIPUS v1.3 — Kuitansi search + export endpoint (Tahap 22).

Endpoint:
- GET /v1/kuitansi/search       — Advanced filter (date range, tipe, nominal, nama)
- GET /v1/kuitansi/export       — Export to CSV / Excel
- GET /v1/kuitansi/{id}         — Detail kuitansi (existing)

Filters:
- date_from, date_to: ISO date (YYYY-MM-DD)
- tipe: x | pt | khusus (filter by which field has value > 0)
- nominal_min, nominal_max: integer (filter by total_pemberian_angka)
- nama: LIKE search (encrypted, decrypt-then-match)
- id_rekap: exact match
- page, per_page: pagination

RBAC:
- BENDAHARA/KETUA/PENDETA: only their tenant
- AUDITOR_MISI: all jemaat in misi
- ADMIN_UNI: all jemaat in uni
"""

import csv
import io
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

if TYPE_CHECKING:  # S4-D.R1: import InstrumentedAttribute only untuk mypy (runtime overhead = 0)
    from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.security import decrypt_pii
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.master import MisiKonferens, Uni, PersentaseConfig
from app.models.audit import AuditLog
# FASE 2 S6/R5: recompute single pakai Jerry Model B (single source of truth).
from app.utils.porsi_calculator import compute_porsi

router = APIRouter()


# ===== Schemas =====

class KuitansiListItem(BaseModel):
    id: int
    nomor_kuitansi: str
    id_rekap_mingguan: str
    tanggal_sabat: str
    nama_umat: Optional[str] = None  # decrypted
    nomor_whatsapp: Optional[str] = None  # decrypted
    perpuluhan_x_angka: int
    pt_angka: int
    khusus_angka: int
    total_pemberian_angka: int
    porsi_kantor_misi: int
    porsi_kas_jemaat: int
    tenant_id: int
    nama_jemaat: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KuitansiSearchOut(BaseModel):
    items: List[KuitansiListItem]
    total: int
    page: int
    per_page: int
    total_pages: int


class FilterMetaOut(BaseModel):
    """Available filter options + counts."""
    total_kuitansi: int
    total_x: int
    total_pt: int
    total_khusus: int
    total_pemberian: int
    date_range_from: Optional[str]
    date_range_to: Optional[str]


# ===== Helpers =====

def _decrypt_kuitansi_fields(k: Kuitansi, db: Session = None, current: dict = None, purpose: str = "search") -> dict:
    """Decrypt PII fields safely. Audit per GDPR right-to-be-informed.

    T89 (Jerry, 2026-08-23): PRIVASI FATAL — nama_umat & nomor_whatsapp HANYA
    boleh di-decrypt untuk BENDAHARA / PENDETA. Role lain (AUDITOR_MISI,
    ADMIN_UNI, KETUA_KEUANGAN) dapat masked ("Umat #kuitansi") agar tidak
    lihat identitas individu (mereka boleh lihat aggregate, BUKAN PII).

    Frontend WA blast Bendahara→Ketua sudah mask nama via `sanitize_nama_for_ketua`.
    Search/Export endpoint pakai helper ini untuk konsistensi privacy.
    """
    # T89: Cek role — hanya BENDAHARA & PENDETA boleh lihat PII.
    can_see_pii = (
        current is not None
        and current.get("role") in ("BENDAHARA", "PENDETA")
    )

    if not can_see_pii:
        # Masked: tetap muncul "Umat #ID" supaya list tidak kosong visually,
        # tapi identitas asli tidak terexpose.
        nama_umat = f"Umat #{k.id}" if k.nama_umat_encrypted else None
        nomor_wa = "••••••" if k.nomor_whatsapp_encrypted else None
        return {"nama_umat": nama_umat, "nomor_whatsapp": nomor_wa}

    nama_umat = None
    if k.nama_umat_encrypted:
        try:
            nama_umat = decrypt_pii(k.nama_umat_encrypted)
        except Exception:
            nama_umat = "[decrypt error]"
    nomor_wa = None
    if k.nomor_whatsapp_encrypted:
        try:
            nomor_wa = decrypt_pii(k.nomor_whatsapp_encrypted)
        except Exception:
            nomor_wa = None

    # T78: Audit PII decryption (GDPR Art. 15 — right to be informed).
    # Log setiap akses ke PII umat untuk compliance trail.
    # Skip kalau caller info tidak ada (backward compat dengan internal helper).
    if db is not None and current is not None:
        try:
            from app.models.audit import AuditLog
            db.add(AuditLog(
                tenant_id=k.tenant_id,
                action=(
                    f"PII_DECRYPT_purpose_{purpose}_user_{current['id']}_role_{current['role']}"
                    f"_kuitansi_{k.id}_nomor_{k.nomor_kuitansi}"
                ),
                payload_hash=(nama_umat or "")[:32],
            ))
            db.commit()
        except Exception:
            # Audit failure TIDAK boleh block decrypt — best-effort logging.
            try:
                db.rollback()
            except Exception:
                pass

    return {"nama_umat": nama_umat, "nomor_whatsapp": nomor_wa}


def _get_visible_tenant_ids(db: Session, current: dict) -> List[int]:
    """Return list of tenant IDs visible to caller."""
    role = current["role"]
    caller_tenant = db.query(Tenant).filter(Tenant.id == current["tenant_id"]).first()

    if role in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA"):
        return [caller_tenant.id] if caller_tenant else []

    if role == "AUDITOR_MISI":
        if not caller_tenant or not caller_tenant.misi_konferens_id:
            return []
        return [t.id for t in db.query(Tenant).filter(
            Tenant.misi_konferens_id == caller_tenant.misi_konferens_id
        ).all()]

    if role == "ADMIN_UNI":
        if not caller_tenant or not caller_tenant.nama_uni:
            return []
        uni = db.query(Uni).filter(Uni.nama_resmi == caller_tenant.nama_uni).first()
        if not uni:
            return []
        # Semua misi di uni tsb
        misi_ids = [m.id for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == uni.id).all()]
        return [t.id for t in db.query(Tenant).filter(
            Tenant.misi_konferens_id.in_(misi_ids)
        ).all()]

    return []


def _build_filters(
    db: Session,
    visible_tenant_ids: List[int],
    date_from: Optional[str],
    date_to: Optional[str],
    tipe: Optional[str],
    nominal_min: Optional[int],
    nominal_max: Optional[int],
    id_rekap: Optional[str],
    nama: Optional[str],
):
    """Build SQLAlchemy filter conditions."""
    filters = []

    # Tenant scope (RBAC)
    if not visible_tenant_ids:
        filters.append(Kuitansi.id == -1)  # always false
    else:
        filters.append(Kuitansi.tenant_id.in_(visible_tenant_ids))

    # Purged excluded
    filters.append(Kuitansi.is_purged == False)

    # Date range
    if date_from:
        if not _is_valid_iso_date(date_from):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"date_from '{date_from}' tidak valid (YYYY-MM-DD)")
        filters.append(Kuitansi.tanggal_sabat >= date_from)
    if date_to:
        if not _is_valid_iso_date(date_to):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"date_to '{date_to}' tidak valid (YYYY-MM-DD)")
        filters.append(Kuitansi.tanggal_sabat <= date_to)

    # Tipe filter (which field has value > 0)
    if tipe == "x":
        filters.append(Kuitansi.perpuluhan_x_angka > 0)
    elif tipe == "pt":
        filters.append(Kuitansi.pt_angka > 0)
    elif tipe == "khusus":
        filters.append(Kuitansi.khusus_angka > 0)
    elif tipe == "x_pt":
        filters.append(or_(Kuitansi.perpuluhan_x_angka > 0, Kuitansi.pt_angka > 0))
    elif tipe == "all_has_value":
        filters.append(or_(
            Kuitansi.perpuluhan_x_angka > 0,
            Kuitansi.pt_angka > 0,
            Kuitansi.khusus_angka > 0,
        ))
    elif tipe == "kosong":
        filters.append(Kuitansi.total_pemberian_angka == 0)
    elif tipe is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"tipe '{tipe}' tidak dikenal (x|pt|khusus|x_pt|all_has_value|kosong)")

    # T23-1: Status filter (draft|finalized|rejected|all)
    # Note: filtered directly in caller to pass 'all' correctly

    # Nominal range
    if nominal_min is not None:
        if nominal_min < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "nominal_min harus >= 0")
        filters.append(Kuitansi.total_pemberian_angka >= nominal_min)
    if nominal_max is not None:
        if nominal_max < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "nominal_max harus >= 0")
        filters.append(Kuitansi.total_pemberian_angka <= nominal_max)

    # id_rekap
    if id_rekap:
        filters.append(Kuitansi.id_rekap_mingguan == id_rekap.strip())

    return filters, nama


def _apply_nama_filter(db: Session, q, nama: Optional[str]):
    """Filter by nama (LIKE, decrypt-then-match)."""
    if not nama:
        return q
    # Karena nama_encrypted, kita fetch dulu + filter in Python (slow tapi OK untuk dataset kecil)
    # Untuk optimasi, fetch semua candidate dengan tenant scope, decrypt, filter
    # Mungkin di kemudian hari perlu FTS table
    all_candidates = q.all()
    matching_ids = []
    nama_lower = nama.lower().strip()
    for k in all_candidates:
        if k.nama_umat_encrypted:
            try:
                nama_dec = decrypt_pii(k.nama_umat_encrypted)
                if nama_dec and nama_lower in nama_dec.lower():
                    matching_ids.append(k.id)
            except Exception:
                pass
    if not matching_ids:
        return q.filter(Kuitansi.id == -1)  # empty
    return q.filter(Kuitansi.id.in_(matching_ids))


def _is_valid_iso_date(s: str) -> bool:
    if not s or len(s) < 10:
        return False
    try:
        datetime.fromisoformat(s[:10])
        return True
    except ValueError:
        return False


# ===== Endpoints =====

@router.get("/search", tags=['Kuitansi'], response_model=KuitansiSearchOut)
def search_kuitansi(
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    tipe: Optional[str] = Query(None, description="x|pt|khusus|x_pt|all_has_value|kosong"),
    status_filter: Optional[str] = Query("finalized", description="T23-1: draft|finalized|rejected|all"),  # T23-1: default finalized
    nominal_min: Optional[int] = Query(None, ge=0),
    nominal_max: Optional[int] = Query(None, ge=0),
    id_rekap: Optional[str] = Query(None),
    nama: Optional[str] = Query(None, description="LIKE search (decrypt-then-match)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    sort_by: str = Query("tanggal_sabat", description="tanggal_sabat|nominal|created_at"),
    sort_order: str = Query("desc", description="asc|desc"),
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Advanced search kuitansi dengan multiple filters.

    T23-1: Default status_filter='finalized' (hanya approved).
    Gunakan status_filter='all' untuk lihat draft juga (Bendahara/Auditor).

    Returns:
        items: list of matching kuitansi (decrypted)
        total: total count sebelum pagination
        page, per_page, total_pages
    """
    if status_filter not in ("draft", "finalized", "rejected", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status_filter harus 'draft'|'finalized'|'rejected'|'all'")

    visible_tenant_ids = _get_visible_tenant_ids(db, current)

    # Build base query
    filters, _ = _build_filters(
        db, visible_tenant_ids,
        date_from, date_to, tipe,
        nominal_min, nominal_max, id_rekap, nama,
    )
    # Status filter
    if status_filter != "all":
        filters.append(Kuitansi.status == status_filter)
    q = db.query(Kuitansi).filter(and_(*filters))

    # Nama filter (decrypt-then-match)
    if nama:
        q = _apply_nama_filter(db, q, nama)

    # Count before pagination
    total = q.count()

    # Sort — type hint only (import ada di top-of-file TYPE_CHECKING)
    sort_col: InstrumentedAttribute = {
        "tanggal_sabat": Kuitansi.tanggal_sabat,
        "nominal": Kuitansi.total_pemberian_angka,
        "created_at": Kuitansi.created_at,
    }.get(sort_by, Kuitansi.tanggal_sabat)
    if sort_order == "asc":
        q = q.order_by(sort_col.asc())
    else:
        q = q.order_by(sort_col.desc())

    # Pagination
    offset = (page - 1) * per_page
    rows = q.offset(offset).limit(per_page).all()

    # Build tenant lookup
    tenant_map = {t.id: t for t in db.query(Tenant).filter(Tenant.id.in_(visible_tenant_ids)).all()}

    items = []
    for k in rows:
        # T89: Pass current untuk role-check — non-BENDAHARA/PENDETA dapat masked.
        decrypted = _decrypt_kuitansi_fields(k, db=db, current=current, purpose="search")
        items.append(KuitansiListItem(
            id=k.id,
            nomor_kuitansi=k.nomor_kuitansi,
            id_rekap_mingguan=k.id_rekap_mingguan,
            tanggal_sabat=k.tanggal_sabat,
            nama_umat=decrypted["nama_umat"],
            nomor_whatsapp=decrypted["nomor_whatsapp"],
            perpuluhan_x_angka=k.perpuluhan_x_angka,
            pt_angka=k.pt_angka,
            khusus_angka=k.khusus_angka,
            total_pemberian_angka=k.total_pemberian_angka,
            porsi_kantor_misi=k.porsi_kantor_misi,
            porsi_kas_jemaat=k.porsi_kas_jemaat,
            tenant_id=k.tenant_id,
            nama_jemaat=tenant_map[k.tenant_id].nama_jemaat_lokal if k.tenant_id in tenant_map else None,
        ))

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"KUITANSI_SEARCH_user_{current['id']}_filters={date_from or '*'}_{date_to or '*'}_{tipe or '*'}_status={status_filter}",
        payload_hash=f"total={total}",
    ))
    db.commit()

    return KuitansiSearchOut(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/filter-meta", tags=['Kuitansi'], response_model=FilterMetaOut)
def filter_meta(
    status_filter: Optional[str] = Query("finalized", description="T23-1: draft|finalized|rejected|all"),
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """Return aggregate stats untuk current filter context. Useful untuk chart awal."""
    if status_filter not in ("draft", "finalized", "rejected", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status_filter harus 'draft'|'finalized'|'rejected'|'all'")

    visible_tenant_ids = _get_visible_tenant_ids(db, current)
    if not visible_tenant_ids:
        return FilterMetaOut(
            total_kuitansi=0, total_x=0, total_pt=0, total_khusus=0,
            total_pemberian=0, date_range_from=None, date_range_to=None,
        )

    q = db.query(Kuitansi).filter(
        Kuitansi.tenant_id.in_(visible_tenant_ids),
        Kuitansi.is_purged == False,
    )
    if status_filter != "all":
        q = q.filter(Kuitansi.status == status_filter)

    agg = q.with_entities(
        func.count(Kuitansi.id).label("total"),
        func.coalesce(func.sum(Kuitansi.perpuluhan_x_angka), 0).label("total_x"),
        func.coalesce(func.sum(Kuitansi.pt_angka), 0).label("total_pt"),
        func.coalesce(func.sum(Kuitansi.khusus_angka), 0).label("total_khusus"),
        func.coalesce(func.sum(Kuitansi.total_pemberian_angka), 0).label("total_pemberian"),
        func.min(Kuitansi.tanggal_sabat).label("min_date"),
        func.max(Kuitansi.tanggal_sabat).label("max_date"),
    ).first()
    if agg is None:
        return FilterMetaOut(
            total_kuitansi=0, total_x=0, total_pt=0, total_khusus=0,
            total_pemberian=0, date_range_from=None, date_range_to=None,
        )  # S4-D.R1: handle empty result for mypy + safety

    return FilterMetaOut(
        total_kuitansi=agg.total,
        total_x=agg.total_x,
        total_pt=agg.total_pt,
        total_khusus=agg.total_khusus,
        total_pemberian=agg.total_pemberian,
        date_range_from=agg.min_date,
        date_range_to=agg.max_date,
    )


# ===== Export =====

@router.get("/export", tags=['Kuitansi'])
def export_kuitansi(
    format: str = Query("csv", description="csv|xlsx|pdf"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    tipe: Optional[str] = Query(None),
    status_filter: Optional[str] = Query("finalized", description="T23-1: draft|finalized|rejected|all"),
    nominal_min: Optional[int] = Query(None),
    nominal_max: Optional[int] = Query(None),
    id_rekap: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    Export filtered kuitansi ke CSV, Excel, atau PDF.

    T23-1: Default status_filter='finalized'. Pakai 'all' untuk export draft juga.

    T73: tambah format=pdf untuk backup/archive list kuitansi (landscape, branding-aware).

    Digunakan oleh Auditor/Admin untuk analisis offline (spreadsheet) atau arsip PDF.
    """
    if format not in ("csv", "xlsx", "pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format harus 'csv'|'xlsx'|'pdf'")
    if status_filter not in ("draft", "finalized", "rejected", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status_filter harus 'draft'|'finalized'|'rejected'|'all'")

    visible_tenant_ids = _get_visible_tenant_ids(db, current)

    filters, _ = _build_filters(
        db, visible_tenant_ids,
        date_from, date_to, tipe,
        nominal_min, nominal_max, id_rekap, None,
    )
    if status_filter != "all":
        filters.append(Kuitansi.status == status_filter)
    q = db.query(Kuitansi).filter(and_(*filters)).order_by(Kuitansi.tanggal_sabat.desc())
    rows = q.all()

    # Build tenant map
    tenant_map = {t.id: t for t in db.query(Tenant).filter(Tenant.id.in_(visible_tenant_ids)).all()}

    # Header
    headers = [
        "ID", "Nomor Kuitansi", "ID Rekap", "Tanggal Sabat", "Jemaat",
        "Nama Umat", "Nomor WA", "X", "PT", "Khusus", "Total",
        "Porsi Misi", "Porsi Jemaat",
    ]

    if format == "csv":
        return _export_csv(db, rows, tenant_map, headers, current)
    elif format == "xlsx":
        return _export_xlsx(db, rows, tenant_map, headers, current)
    else:
        return _export_pdf(db, rows, tenant_map, headers, current)


# ===== v1.5-B: Per-kuitansi PDF generator =====

@router.get("/{kuitansi_id}/pdf", tags=['Kuitansi'])
def get_kuitansi_pdf(
    kuitansi_id: int,
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
):
    """
    v1.5-B: Generate single-kuitansi PDF (FLIPUS branding, A4 portrait).

    Cocok untuk:
    - Auto-thanks WA (kirim PDF lampiran ke umat individual)
    - Download arsip satu kuitansi
    - Print ke printer

    RBAC: tenant-scoped (BENDAHARA/PENDETA own tenant, AUDITOR/ADMIN uni-scope).
    T89: PII masking — non-BENDAHARA/PENDETA dapat masked.
    """
    from fastapi.responses import StreamingResponse
    from app.utils.number_to_words import rupiah_to_words
    try:
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "reportlab belum terinstall — pip install reportlab",
        )

    # Fetch kuitansi dengan tenant-scope RBAC
    visible_tenant_ids = _get_visible_tenant_ids(db, current)
    k = db.query(Kuitansi).filter(
        Kuitansi.id == kuitansi_id,
        Kuitansi.tenant_id.in_(visible_tenant_ids),
        Kuitansi.is_purged == False,
    ).first()
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kuitansi tidak ditemukan / di luar scope Anda")

    tenant = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
    decrypted = _decrypt_kuitansi_fields(k, db=db, current=current, purpose="export_pdf")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    COLOR_PRIMARY = rl_colors.HexColor("#1B4332")
    COLOR_GOLD = rl_colors.HexColor("#B8860B")
    COLOR_BORDER = rl_colors.HexColor("#e5e7eb")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=18, textColor=COLOR_PRIMARY,
        alignment=1, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=10, textColor=rl_colors.grey,
        alignment=1, spaceAfter=14,
    )
    label_style = ParagraphStyle(
        "label", parent=styles["Normal"], fontSize=9, textColor=rl_colors.grey,
        alignment=0,
    )
    value_style = ParagraphStyle(
        "value", parent=styles["Normal"], fontSize=11,
        fontName="Helvetica-Bold", textColor=rl_colors.black, alignment=0,
    )
    total_label_style = ParagraphStyle(
        "tot_label", parent=styles["Normal"], fontSize=10, fontName="Helvetica-Bold",
        textColor=rl_colors.white, alignment=0,
    )
    total_value_style = ParagraphStyle(
        "tot_val", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
        textColor=rl_colors.white, alignment=2,
    )

    elements = []

    # === HEADER ===
    elements.append(Paragraph("TANDA TERIMA PERPULUHAN", title_style))
    sub_text = (
        f"{tenant.nama_uni if tenant else 'GMAHK'} &nbsp;•&nbsp; "
        f"{tenant.nama_kantor_misi if tenant else 'Kantor Misi'} &nbsp;•&nbsp; "
        f"{tenant.nama_jemaat_lokal if tenant else 'Jemaat'}"
    )
    elements.append(Paragraph(sub_text, sub_style))

    # === INFO GRID (No Kuitansi | Tanggal Sabat) ===
    def _fmt_rupiah(n):
        return f"Rp {n:,}".replace(",", ".") if n else "Rp 0"

    info_data = [
        [
            Paragraph("<b>No. Kuitansi</b>", label_style),
            Paragraph(k.nomor_kuitansi or f"#{k.id}", value_style),
            Paragraph("<b>Tanggal Sabat</b>", label_style),
            Paragraph(k.tanggal_sabat, value_style),
        ],
        [
            Paragraph("<b>Nama Umat</b>", label_style),
            Paragraph(decrypted.get("nama_umat") or "—", value_style),
            Paragraph("<b>Status</b>", label_style),
            Paragraph((k.status or "draft").upper(), value_style),
        ],
        [
            Paragraph("<b>ID Rekap Mingguan</b>", label_style),
            Paragraph(k.id_rekap_mingguan or "—", value_style),
            Paragraph("<b>Nomor WA</b>", label_style),
            Paragraph(decrypted.get("nomor_whatsapp") or "—", value_style),
        ],
    ]
    info_table = Table(info_data, colWidths=[3.5 * cm, 5 * cm, 3.5 * cm, 5 * cm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (1, 0), (1, -1), 0.5, COLOR_BORDER),
        ("LINEBELOW", (3, 0), (3, -1), 0.5, COLOR_BORDER),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.8 * cm))

    # === RINCIAN TABLE ===
    elements.append(Paragraph("<b>Rincian Pemberian</b>", value_style))
    elements.append(Spacer(1, 0.3 * cm))

    total = k.total_pemberian_angka or 0
    rincian_data = [
        ["", "Jumlah (Rp)"],
        ["Perpuluhan (X)", _fmt_rupiah(k.perpuluhan_x_angka)],
        ["Persembahan Terpadu (PT)", _fmt_rupiah(k.pt_angka)],
        ["Persembahan Khusus", _fmt_rupiah(k.khusus_angka)],
    ]
    rincian_table = Table(rincian_data, colWidths=[10 * cm, 6 * cm])
    rincian_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#fef9e7")]),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(rincian_table)
    elements.append(Spacer(1, 0.3 * cm))

    # === TOTAL + TERBILANG ===
    try:
        text_terbilang = rupiah_to_words(total)
    except Exception:
        text_terbilang = f"{total:,}".replace(",", ".") + " rupiah"

    total_data = [
        [
            Paragraph("TOTAL", total_label_style),
            Paragraph(_fmt_rupiah(total), total_value_style),
        ],
        [
            Paragraph("<i>Terbilang:</i>", ParagraphStyle("tb", parent=label_style, fontSize=8)),
            Paragraph(f"<i>{text_terbilang}</i>", ParagraphStyle("tv", parent=label_style, fontSize=8, alignment=2)),
        ],
    ]
    total_table = Table(total_data, colWidths=[10 * cm, 6 * cm])
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 0.6 * cm))

    # === DISTRIBUSI PORSI ===
    elements.append(Paragraph("<b>Penyaluran</b>", value_style))
    elements.append(Spacer(1, 0.2 * cm))
    porsi_data = [
        ["", "Jumlah (Rp)"],
        ["Kantor Misi", _fmt_rupiah(k.porsi_kantor_misi)],
        ["Kas Jemaat", _fmt_rupiah(k.porsi_kas_jemaat)],
    ]
    porsi_table = Table(porsi_data, colWidths=[10 * cm, 6 * cm])
    porsi_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_GOLD),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(porsi_table)
    elements.append(Spacer(1, 1.2 * cm))

    # === SIGNATURE BLOCK ===
    sig_data = [
        [
            Paragraph("Bendahara", ParagraphStyle("s1", parent=label_style, alignment=1)),
            Paragraph("Penerima / Umat", ParagraphStyle("s2", parent=label_style, alignment=1)),
        ],
        [
            Paragraph("<br/><br/><br/><br/>", label_style),
            Paragraph("<br/><br/><br/><br/>", label_style),
        ],
        [
            Paragraph(
                f"<b>({tenant.nama_bendahara if tenant and tenant.nama_bendahara else '—'})</b>",
                ParagraphStyle("sn1", parent=label_style, alignment=1, fontName="Helvetica-Bold"),
            ),
            Paragraph(
                f"<b>{decrypted.get('nama_umat') or '—'}</b>",
                ParagraphStyle("sn2", parent=label_style, alignment=1, fontName="Helvetica-Bold"),
            ),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[8 * cm, 8 * cm])
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(sig_table)

    # === FOOTER ===
    elements.append(Spacer(1, 0.6 * cm))
    footer_style = ParagraphStyle(
        "foot", parent=styles["Normal"], fontSize=8, textColor=rl_colors.grey,
        alignment=1,
    )
    elements.append(Paragraph(
        "Dokumen ini digenerate otomatis oleh FLIPUS — UKIKT GMAHK. "
        "Simpan sebagai arsip pribadi Anda.",
        footer_style,
    ))

    doc.build(elements)
    buffer.seek(0)

    # Audit log
    db.add(AuditLog(
        tenant_id=k.tenant_id,
        id_rekap_mingguan=k.id_rekap_mingguan,
        nomor_kuitansi_token=k.nomor_kuitansi[:32] if k.nomor_kuitansi else None,
        action=f"KUITANSI_PDF_DOWNLOAD_user_{current['id']}_k_{k.id}",
        payload_hash=f"format=pdf_single",
    ))
    db.commit()

    pdf_filename = f"kuitansi-{k.nomor_kuitansi or k.id}.pdf".replace("/", "_")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{pdf_filename}"',
        },
    )


def _export_csv(
    db: Session,
    rows: List[Kuitansi],
    tenant_map: dict,
    headers: List[str],
    current: dict,
) -> StreamingResponse:
    """Generate CSV streaming response."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for k in rows:
        # T89 (Jerry, 2026-08-23): PRIVASI FATAL — pass current role.
        # Non-BENDAHARA/PENDETA dapat "Umat #ID" + "••••••", bukan nama/angka asli.
        decrypted = _decrypt_kuitansi_fields(k, db=db, current=current, purpose="export_csv")
        nama_jemaat = tenant_map[k.tenant_id].nama_jemaat_lokal if k.tenant_id in tenant_map else ""
        writer.writerow([
            k.id,
            k.nomor_kuitansi,
            k.id_rekap_mingguan,
            k.tanggal_sabat,
            nama_jemaat,
            decrypted["nama_umat"] or "",
            decrypted["nomor_whatsapp"] or "",
            k.perpuluhan_x_angka,
            k.pt_angka,
            k.khusus_angka,
            k.total_pemberian_angka,
            k.porsi_kantor_misi,
            k.porsi_kas_jemaat,
        ])

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"KUITANSI_EXPORT_CSV_user_{current['id']}_count_{len(rows)}",
        payload_hash=f"format=csv",
    ))
    db.commit()

    csv_content = output.getvalue()
    output.close()

    filename = f"kuitansi_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _export_xlsx(
    db: Session,
    rows: List[Kuitansi],
    tenant_map: dict,
    headers: List[str],
    current: dict,
) -> StreamingResponse:
    """Generate XLSX streaming response. Requires openpyxl."""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "openpyxl belum terinstall — pip install openpyxl",
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Kuitansi"

    # Headers (bold)
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1B4332", end_color="1B4332", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for k in rows:
        # T89 (Jerry, 2026-08-23): PRIVASI FATAL — pass current role.
        # Non-BENDAHARA/PENDETA dapat "Umat #ID" + "••••••", bukan nama/angka asli.
        decrypted = _decrypt_kuitansi_fields(k, db=db, current=current, purpose="export_xlsx")
        nama_jemaat = tenant_map[k.tenant_id].nama_jemaat_lokal if k.tenant_id in tenant_map else ""
        ws.append([
            k.id,
            k.nomor_kuitansi,
            k.id_rekap_mingguan,
            k.tanggal_sabat,
            nama_jemaat,
            decrypted["nama_umat"] or "",
            decrypted["nomor_whatsapp"] or "",
            k.perpuluhan_x_angka,
            k.pt_angka,
            k.khusus_angka,
            k.total_pemberian_angka,
            k.porsi_kantor_misi,
            k.porsi_kas_jemaat,
        ])

    # Auto-size columns — safe approach using column letter
    for column_idx in range(1, ws.max_column + 1):
        col_letter = get_column_letter(column_idx)
        try:
            max_length = max(
                (len(str(ws.cell(row=r, column=column_idx).value or "")) for r in range(1, ws.max_row + 1)),
                default=0,
            )
            ws.column_dimensions[col_letter].width = min(max_length + 2, 50)
        except Exception:
            # If any column has issues, skip auto-size for it
            pass

    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    xlsx_bytes = output.getvalue()
    output.close()

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"KUITANSI_EXPORT_XLSX_user_{current['id']}_count_{len(rows)}",
        payload_hash=f"format=xlsx",
    ))
    db.commit()

    filename = f"kuitansi_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ===== T73: PDF Export =====
#
# Pakai reportlab Platypus untuk generate PDF list kuitansi (landscape, branding-aware).
# Tujuannya: backup/archive — bukan laporan keuangan per sabat (yang sudah ada di
# /v1/reports/keuangan). PDF ini adalah "raw kuitansi list" dengan header tenant.

def _export_pdf(
    db: Session,
    rows: List[Kuitansi],
    tenant_map: dict,
    headers: List[str],
    current: dict,
) -> StreamingResponse:
    """Generate PDF list kuitansi (landscape, FLIPUS branding). T73.

    Requires reportlab. Pakai Platypus SimpleDocTemplate.
    """
    try:
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
    except ImportError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "reportlab belum terinstall — pip install reportlab",
        )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),  # landscape karena kolom banyak
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    elements = []

    # FLIPUS brand colors
    COLOR_PRIMARY = rl_colors.HexColor("#1B4332")  # green tua
    COLOR_GOLD = rl_colors.HexColor("#B8860B")
    COLOR_BORDER = rl_colors.HexColor("#e5e7eb")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title", parent=styles["Heading1"],
        fontName="Helvetica-Bold", fontSize=14, textColor=COLOR_PRIMARY,
        alignment=1, spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=9, textColor=rl_colors.grey,
        alignment=1, spaceAfter=10,
    )

    # === TITLE BLOCK ===
    elements.append(Paragraph("FLIPUS — Daftar Kuitansi", title_style))
    sub_text = (
        f"Digenerate: {datetime.now().strftime('%d %B %Y %H:%M')} "
        f"&nbsp;|&nbsp; Total: <b>{len(rows)}</b> kuitansi"
    )
    elements.append(Paragraph(sub_text, sub_style))

    # === TABEL KUITANSI ===
    # Skip kolom "ID" dan "Nomor WA" untuk PDF ringkas; sisanya tampil.
    pdf_headers = ["No", "No. Kuitansi", "Tgl Sabat", "Jemaat", "Nama Umat",
                   "X", "PT", "KH", "Total", "Porsi Misi", "Porsi Jemaat"]
    data = [pdf_headers]

    for idx, k in enumerate(rows, 1):
        # T89: PRIVASI FATAL — non-BENDAHARA/PENDETA dapat masked.
        decrypted = _decrypt_kuitansi_fields(k, db=db, current=current, purpose="export_pdf")
        nama_jemaat = tenant_map[k.tenant_id].nama_jemaat_lokal if k.tenant_id in tenant_map else ""
        # Truncate nama_jemaat agar tidak overflow kolom
        nama_jemaat_short = (nama_jemaat[:22] + "…") if len(nama_jemaat) > 23 else nama_jemaat
        # Truncate nama umat juga
        nama_umat_raw = decrypted["nama_umat"] or ""
        nama_umat_short = (nama_umat_raw[:24] + "…") if len(nama_umat_raw) > 25 else nama_umat_raw
        # Format rupiah ringkas (singkat "Rp " prefix untuk hemat ruang)
        def _fmt(n):
            return f"{n:,}".replace(",", ".") if n else "-"
        data.append([
            str(idx),
            Paragraph(k.nomor_kuitansi or f"#{k.id}",
                      ParagraphStyle("mono", fontName="Courier", fontSize=7)),
            k.tanggal_sabat,
            nama_jemaat_short,
            nama_umat_short,
            _fmt(k.perpuluhan_x_angka),
            _fmt(k.pt_angka),
            _fmt(k.khusus_angka) if k.khusus_angka else "-",
            _fmt(k.total_pemberian_angka),
            _fmt(k.porsi_kantor_misi),
            _fmt(k.porsi_kas_jemaat),
        ])

    # Lebar kolom (total ~ 26cm untuk landscape A4 minus margin)
    col_widths = [
        0.8 * cm,   # No
        3.5 * cm,   # No. Kuitansi
        1.8 * cm,   # Tgl Sabat
        3.8 * cm,   # Jemaat
        3.8 * cm,   # Nama Umat
        2.0 * cm,   # X
        2.0 * cm,   # PT
        1.8 * cm,   # KH
        2.2 * cm,   # Total
        2.2 * cm,   # Porsi Misi
        2.2 * cm,   # Porsi Jemaat
    ]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("ALIGN", (5, 1), (-1, -1), "RIGHT"),  # rupiah columns right-aligned
        ("ALIGN", (0, 1), (0, -1), "CENTER"),  # No center
        # Borders
        ("GRID", (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("BOX", (0, 0), (-1, -1), 0.8, COLOR_PRIMARY),
        # Zebra striping untuk readability
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAF9F5")]),
    ]))
    elements.append(table)

    # === FOOTER ===
    elements.append(Spacer(1, 12))
    footer_text = (
        f"<i>Dokumen ini digenerate otomatis oleh FLIPUS — Sistem Akuntansi Jemaat GMAHK UKIKT. "
        f"User: {current.get('role', 'unknown')} · Tenant ID: {current.get('tenant_id', '?')} · "
        f"Generated by: user_id={current['id']}</i>"
    )
    elements.append(Paragraph(
        footer_text,
        ParagraphStyle("footer", fontSize=7, textColor=rl_colors.grey, alignment=1),
    ))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    # Audit log
    db.add(AuditLog(
        tenant_id=current["tenant_id"],
        action=f"KUITANSI_EXPORT_PDF_user_{current['id']}_count_{len(rows)}",
        payload_hash=f"format=pdf",
    ))
    db.commit()

    filename = f"kuitansi_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ===== FASE 2 S6/R5: Single-Kuitansi Recompute =====

class RecomputePorsiSingleOut(BaseModel):
    """Schema response untuk POST /kuitansi/{id}/recompute-porsi (single).

    Single source of truth policy (R5):
    - Stored snapshot di kuitansi adalah immutable per kuitansi (audit-friendly).
    - Endpoint ini untuk override: kalau Auditor/Admin yakin PersentaseConfig sudah benar
      dan ingin apply ke satu kuitansi spesifik (misal: koreksi manual satu data).
    - Setiap recompute menulis ke audit_logs dengan before/after/config_snapshot
      agar bisa di-trace 100% kenapa porsi berubah dari nilai awalnya.
    """
    status: str
    kuitansi_id: int
    nomor_kuitansi: str
    before: dict
    after: dict
    changed: bool
    porsi_recomputed_at: str
    config_snapshot: dict
    audit_log_id: int


@router.post("/{kuitansi_id}/recompute-porsi", tags=['Kuitansi'], response_model=RecomputePorsiSingleOut)
def recompute_porsi_single(
    kuitansi_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    FASE 2 S6/R5: Recompute porsi untuk SATU kuitansi.

    Path: POST /api/v1/kuitansi/{kuitansi_id}/recompute-porsi

    RBAC:
    - ADMIN_UNI: boleh recompute kuitansi di seluruh uni-nya.
    - AUDITOR_MISI: boleh recompute kuitansi di misi-nya saja.
    - BENDAHARA / KETUA_KEUANGAN / PENDETA: DILARANG (cukup lihat stored snapshot).

    Catatan:
    - Endpoint ini HARUS idempotent: kalau dipanggil 2x dengan config sama,
      nilai before/after akan sama (changed=False), jadi tidak merusak data.
    - Field porsi_recomputed_at di-update ke waktu UTC sekarang setelah recompute.
    - Audit log immutable (append-only) — tidak pernah di-update atau dihapus.
    """
    if current_user["role"] not in ("ADMIN_UNI", "AUDITOR_MISI"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Recompute single hanya untuk ADMIN_UNI / AUDITOR_MISI",
        )

    k = db.query(Kuitansi).filter(Kuitansi.id == kuitansi_id).first()
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Kuitansi #{kuitansi_id} tidak ditemukan")
    if k.is_purged:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kuitansi sudah di-purge, tidak bisa di-recompute")

    # RBAC scope check: ADMIN_UNI = seluruh uni, AUDITOR_MISI = misi-nya saja
    tenant = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
    if not tenant:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tenant kuitansi tidak valid")

    caller = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if current_user["role"] == "ADMIN_UNI":
        if not caller or not caller.nama_uni or tenant.nama_uni != caller.nama_uni:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Kuitansi ini di luar Uni Anda",
            )
    elif current_user["role"] == "AUDITOR_MISI":
        if not tenant.misi_konferens_id or tenant.misi_konferens_id != caller.misi_konferens_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Kuitansi ini di luar Misi Anda",
            )

    # Ambil PersentaseConfig MISI scope (single source of truth config)
    cfg_row = (
        db.query(PersentaseConfig)
        .filter(
            PersentaseConfig.scope == "MISI",
            PersentaseConfig.ref_id == tenant.misi_konferens_id,
        )
        .first()
    )
    if not cfg_row:
        # SDA doctrine defaults
        cfg_x, cfg_pt, cfg_kh = 0.0, 0.5, 0.5
        cfg_xu, cfg_ptu, cfg_khu = 0.0, 0.0, 0.0
        cfg_source = "SDA_DOCTRINE_DEFAULT"
        config_id = None
    else:
        cfg_x = cfg_row.pct_x_jemaat
        cfg_pt = cfg_row.pct_pt_jemaat
        cfg_kh = cfg_row.pct_khusus_jemaat
        cfg_xu = cfg_row.pct_x_uni
        cfg_ptu = cfg_row.pct_pt_uni
        cfg_khu = cfg_row.pct_khusus_uni
        cfg_source = f"PersentaseConfig.id={cfg_row.id}"
        config_id = cfg_row.id

    # Snapshot BEFORE
    before = {
        "porsi_kantor_misi": k.porsi_kantor_misi or 0,
        "porsi_kas_jemaat": k.porsi_kas_jemaat or 0,
        "porsi_khusus_misi": k.porsi_khusus_misi or 0,
        "porsi_khusus_jemaat": k.porsi_khusus_jemaat or 0,
        "porsi_x_uni": k.porsi_x_uni or 0,
        "porsi_pt_uni": k.porsi_pt_uni or 0,
        "porsi_khusus_uni": k.porsi_khusus_uni or 0,
    }

    # Hitung ulang pakai Jerry Model B (compute_porsi)
    porsi = compute_porsi(
        x=k.perpuluhan_x_angka or 0,
        pt=k.pt_angka or 0,
        kh=k.khusus_angka or 0,
        pct_x_jemaat=cfg_x,
        pct_pt_jemaat=cfg_pt,
        pct_khusus_jemaat=cfg_kh,
        pct_x_uni=cfg_xu,
        pct_pt_uni=cfg_ptu,
        pct_khusus_uni=cfg_khu,
    )

    new_kantor_misi = porsi["pm_x"] + porsi["pm_pt"] + porsi["pm_kh"]
    new_kas_jemaat = porsi["pj_x"] + porsi["pj_pt"] + porsi["pj_kh"]

    # Tulis ke DB (snapshot override)
    k.porsi_kantor_misi = new_kantor_misi
    k.porsi_kas_jemaat = new_kas_jemaat
    k.porsi_khusus_misi = porsi["pm_kh"]
    k.porsi_khusus_jemaat = porsi["pj_kh"]
    k.porsi_x_uni = porsi["pu_x"]
    k.porsi_pt_uni = porsi["pu_pt"]
    k.porsi_khusus_uni = porsi["pu_kh"]
    k.porsi_recomputed_at = datetime.now(timezone.utc)

    # Snapshot AFTER
    after = {
        "porsi_kantor_misi": k.porsi_kantor_misi,
        "porsi_kas_jemaat": k.porsi_kas_jemaat,
        "porsi_khusus_misi": k.porsi_khusus_misi,
        "porsi_khusus_jemaat": k.porsi_khusus_jemaat,
        "porsi_x_uni": k.porsi_x_uni,
        "porsi_pt_uni": k.porsi_pt_uni,
        "porsi_khusus_uni": k.porsi_khusus_uni,
    }
    changed = before != after

    # Audit log (immutable, append-only) — FASE 2 S6/R5
    audit = AuditLog(
        tenant_id=k.tenant_id,
        id_rekap_mingguan=k.id_rekap_mingguan,
        nomor_kuitansi_token=k.nomor_kuitansi,
        action="recompute_porsi_single",
        porsi_dana_misi=new_kantor_misi,
        payload_hash=(
            f"kuitansi_id={kuitansi_id}|user_id={current_user['id']}|"
            f"role={current_user['role']}|"
            f"before={before}|after={after}|"
            f"config_source={cfg_source}|config_id={config_id}|"
            f"pct_x_j={cfg_x},pct_pt_j={cfg_pt},pct_kh_j={cfg_kh},"
            f"pct_x_u={cfg_xu},pct_pt_u={cfg_ptu},pct_kh_u={cfg_khu}|"
            f"changed={changed}"
        ),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    return RecomputePorsiSingleOut(
        status="ok",
        kuitansi_id=k.id,
        nomor_kuitansi=k.nomor_kuitansi,
        before=before,
        after=after,
        changed=changed,
        porsi_recomputed_at=k.porsi_recomputed_at.isoformat(),
        config_snapshot={
            "source": cfg_source,
            "pct_x_jemaat": cfg_x,
            "pct_pt_jemaat": cfg_pt,
            "pct_khusus_jemaat": cfg_kh,
            "pct_x_uni": cfg_xu,
            "pct_pt_uni": cfg_ptu,
            "pct_khusus_uni": cfg_khu,
        },
        audit_log_id=audit.id,
    )
