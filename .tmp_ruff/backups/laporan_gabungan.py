"""v2.0 M7 — Laporan Gabungan per Sabat (Kuitansi + Pengeluaran) + PDF + Send-to-Auditor.

Endpoints:
- GET  /laporan/gabungan/{id_rekap_mingguan}              → JSON ringkasan
- GET  /laporan/gabungan/{id_rekap_mingguan}/pdf           → PDF binary
- POST /laporan/gabungan/{id_rekap_mingguan}/send-to-auditor → WA blast ke Auditor Misi

Authorization:
- Bendahara/Ketua/Pendeta/Auditor Misi semua bisa GET (audit transparansi)
- POST send-to-auditor: Bendahara saja
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.tenant_scope import (
    TenantScope, require_tenant_scope,
)
from app.models.transaction import Kuitansi
from app.models.pengeluaran import Pengeluaran
from app.models.kategori_pengeluaran import KategoriPengeluaran
from app.models.tenant import Tenant
from app.models.user import User
from app.models.audit import AuditLog
from app.utils.number_to_words import terbilang
from app.services.pdf_gabungan import generate_gabungan_pdf
from app.services.whatsapp import send_document_message

router = APIRouter()


# ===== Pydantic schemas =====

class KuitansiGabunganItem(BaseModel):
    nomor_kuitansi: str
    perpuluhan_x_angka: int
    pt_angka: int
    khusus_angka: int
    total_pemberian_angka: int
    porsi_kantor_misi: int
    porsi_kas_jemaat: int


class PengeluaranGabunganItem(BaseModel):
    nomor_pengeluaran: str
    kategori_nama: str
    penerima: Optional[str]
    jumlah: int
    status: str
    status_label: str
    created_via: str


class LaporanGabunganOut(BaseModel):
    id_rekap_mingguan: str
    tanggal_sabat: str
    nama_jemaat: str
    nama_uni: str
    nama_kantor_misi: str
    total_penerimaan: int
    total_penerimaan_huruf: str
    total_pengeluaran_approved: int
    total_pengeluaran_approved_huruf: str
    total_pengeluaran_pending: int
    net_saldo: int
    net_saldo_huruf: str
    porsi_misi: int
    porsi_jemaat: int
    count_kuitansi: int
    count_pengeluaran_approved: int
    count_pengeluaran_pending: int
    kuitansi: List[KuitansiGabunganItem]
    pengeluaran: List[PengeluaranGabunganItem]


class SendToAuditorOut(BaseModel):
    status: str
    id_rekap_mingguan: str
    pdf_path: Optional[str] = None
    pdf_filename: Optional[str] = None
    auditors_found: int
    auditors_notified: int
    auditors_skipped: List[dict]  # [{"auditor_id": int, "reason": "no_whatsapp"}, ...]


# ===== Helpers =====

def _status_to_label(s: str) -> str:
    return {
        "approved": "Disetujui",
        "approved_ketua": "Approved Ketua",
        "pending_approval": "Pending",
        "draft": "Draft",
        "rejected": "Ditolak",
    }.get(s, s)


def _require_role(scope: "TenantScope", allowed: List[str]):
    """FASE4-S6E: helper pakai TenantScope.role (single source of truth)."""
    if scope.role not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Akses ditolak. Butuh role: {', '.join(allowed)}",
        )


# ===== Endpoint 1: GET JSON ringkasan gabungan =====

@router.get("/laporan/gabungan/{id_rekap_mingguan}", tags=['Laporan'], response_model=LaporanGabunganOut)
def get_laporan_gabungan(
    id_rekap_mingguan: str,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """Laporan gabungan per sabat: Kuitansi (penerimaan) + Pengeluaran (pengeluaran) + net saldo.

    FASE4-S6E: pakai TenantScope.visible_tenant_ids (cross-tenant audit aware).
    Untuk tenant tampilan, pakai primary_tenant_id.

    RBAC: Bendahara, Ketua, Pendeta, Auditor Misi (semua role yang terkait tenant ini)
    """
    primary_tenant_id = scope.primary_tenant_id
    if not primary_tenant_id:
        raise HTTPException(400, "User tidak terkait dengan tenant/jemaat")

    # Load tenant (display info)
    tenant = db.query(Tenant).filter(Tenant.id == primary_tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    # Load Kuitansi (finalized only — sama dengan laporan_mingguan)
    kuitansi_rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Kuitansi.is_purged == False)
        .filter(Kuitansi.status == "finalized")
        .order_by(Kuitansi.nomor_kuitansi.asc())
        .all()
    )

    # Load Pengeluaran (semua status, kecuali draft pribadi Bendahara)
    # Untuk rekap mingguan, tampilkan approved + pending (visible untuk audit)
    pengeluaran_rows = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.is_purged == False)
        .filter(Pengeluaran.status != "draft")  # exclude draft
        .order_by(Pengeluaran.nomor_pengeluaran.asc())
        .all()
    )

    # Kategori map
    kat_ids = list({p.kategori_pengeluaran_id for p in pengeluaran_rows})
    kat_map = {}
    if kat_ids:
        kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id.in_(kat_ids)).all()
        kat_map = {k.id: k for k in kats}

    # Build items
    kuitansi_items = [
        KuitansiGabunganItem(
            nomor_kuitansi=k.nomor_kuitansi,
            perpuluhan_x_angka=k.perpuluhan_x_angka or 0,
            pt_angka=k.pt_angka or 0,
            khusus_angka=k.khusus_angka or 0,
            total_pemberian_angka=k.total_pemberian_angka or 0,
            porsi_kantor_misi=k.porsi_kantor_misi or 0,
            porsi_kas_jemaat=k.porsi_kas_jemaat or 0,
        )
        for k in kuitansi_rows
    ]

    pengeluaran_items = [
        PengeluaranGabunganItem(
            nomor_pengeluaran=p.nomor_pengeluaran,
            kategori_nama=kat_map[p.kategori_pengeluaran_id].nama if p.kategori_pengeluaran_id in kat_map else f"#{p.kategori_pengeluaran_id}",
            penerima=p.penerima,
            jumlah=p.jumlah or 0,
            status=p.status,
            status_label=_status_to_label(p.status),
            created_via=p.created_via or "web",
        )
        for p in pengeluaran_rows
    ]

    # Aggregates
    total_penerimaan = sum(k.total_pemberian_angka or 0 for k in kuitansi_rows)
    total_peng_approved = sum(
        (p.jumlah or 0) for p in pengeluaran_rows if p.status == "approved"
    )
    total_peng_pending = sum(
        (p.jumlah or 0) for p in pengeluaran_rows if p.status in ("pending_approval", "approved_ketua")
    )
    net_saldo = total_penerimaan - total_peng_approved
    porsi_misi = sum(k.porsi_kantor_misi or 0 for k in kuitansi_rows)
    porsi_jemaat = sum(k.porsi_kas_jemaat or 0 for k in kuitansi_rows)

    # tanggal_sabat: ambil dari kuitansi pertama atau pengeluaran pertama
    tanggal_sabat = "?"
    if kuitansi_rows:
        tanggal_sabat = kuitansi_rows[0].tanggal_sabat
    elif pengeluaran_rows:
        tanggal_sabat = pengeluaran_rows[0].tanggal_sabat

    return LaporanGabunganOut(
        id_rekap_mingguan=id_rekap_mingguan,
        tanggal_sabat=tanggal_sabat,
        nama_jemaat=tenant.nama_jemaat_lokal or "?",
        nama_uni=tenant.nama_uni or "?",
        nama_kantor_misi=tenant.nama_kantor_misi or "?",
        total_penerimaan=total_penerimaan,
        total_penerimaan_huruf=terbilang(total_penerimaan),
        total_pengeluaran_approved=total_peng_approved,
        total_pengeluaran_approved_huruf=terbilang(total_peng_approved),
        total_pengeluaran_pending=total_peng_pending,
        net_saldo=net_saldo,
        net_saldo_huruf=terbilang(net_saldo),
        porsi_misi=porsi_misi,
        porsi_jemaat=porsi_jemaat,
        count_kuitansi=len(kuitansi_rows),
        count_pengeluaran_approved=sum(1 for p in pengeluaran_rows if p.status == "approved"),
        count_pengeluaran_pending=sum(1 for p in pengeluaran_rows if p.status in ("pending_approval", "approved_ketua")),
        kuitansi=kuitansi_items,
        pengeluaran=pengeluaran_items,
    )


# ===== Endpoint 2: GET PDF gabungan =====

@router.get("/laporan/gabungan/{id_rekap_mingguan}/pdf", tags=['Laporan'])
def get_laporan_gabungan_pdf(
    id_rekap_mingguan: str,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """Generate PDF laporan gabungan (Kuitansi + Pengeluaran).

    FASE4-S6E: pakai TenantScope (visible_tenant_ids + primary_tenant_id).
    """
    primary_tenant_id = scope.primary_tenant_id
    if not primary_tenant_id:
        raise HTTPException(400, "User tidak terkait dengan tenant/jemaat")

    tenant = db.query(Tenant).filter(Tenant.id == primary_tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    kuitansi_rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Kuitansi.is_purged == False)
        .filter(Kuitansi.status == "finalized")
        .order_by(Kuitansi.nomor_kuitansi.asc())
        .all()
    )
    pengeluaran_rows = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.is_purged == False)
        .filter(Pengeluaran.status != "draft")
        .order_by(Pengeluaran.nomor_pengeluaran.asc())
        .all()
    )

    kat_ids = list({p.kategori_pengeluaran_id for p in pengeluaran_rows})
    kat_map = {}
    if kat_ids:
        kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id.in_(kat_ids)).all()
        kat_map = {k.id: k for k in kats}

    # Determine tanggal_sabat
    if kuitansi_rows:
        tanggal_sabat = kuitansi_rows[0].tanggal_sabat
    elif pengeluaran_rows:
        tanggal_sabat = pengeluaran_rows[0].tanggal_sabat
    else:
        raise HTTPException(404, "Tidak ada Kuitansi/Pengeluaran untuk rekap ini")

    # Save PDF to storage/temp/<id>.pdf + return bytes
    pdf_dir = Path(os.path.join(os.getcwd(), "storage", "temp"))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"GABUNGAN_{id_rekap_mingguan.replace('/', '_')}.pdf"
    pdf_path = pdf_dir / pdf_filename

    try:
        generate_gabungan_pdf(
            kuitansi_list=kuitansi_rows,
            pengeluaran_list=pengeluaran_rows,
            tenant=tenant,
            id_rekap_mingguan=id_rekap_mingguan,
            tanggal_sabat_iso=str(tanggal_sabat),
            kategori_map=kat_map,
            output_path=str(pdf_path),
        )
    except Exception as exc:
        print(f"[LAPORAN-GABUNGAN-PDF] error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise HTTPException(500, f"Gagal generate PDF: {type(exc).__name__}: {str(exc)[:200]}")

    # Audit log
    try:
        db.add(AuditLog(
            tenant_id=primary_tenant_id,
            action=f"LAPORAN_GABUNGAN_PDF_id_rekap_{id_rekap_mingguan}_by_user_{scope.user_id}_kuitansi_{len(kuitansi_rows)}_pengeluaran_{len(pengeluaran_rows)}",
        ))
        db.commit()
    except Exception as exc:
        print(f"[LAPORAN-GABUNGAN-PDF] audit log error: {exc}", file=sys.stderr, flush=True)
        db.rollback()

    # Read file & return as response
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{pdf_filename}"',
        },
    )


# ===== Endpoint 3: POST send-to-auditor (WA blast) =====

@router.post("/laporan/gabungan/{id_rekap_mingguan}/send-to-auditor", tags=['Laporan'], response_model=SendToAuditorOut)
def send_laporan_gabungan_to_auditor(
    id_rekap_mingguan: str,
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """Generate PDF gabungan + kirim via Fonnte ke semua AUDITOR_MISI di tenant.

    FASE4-S6E: pakai TenantScope. Auditor dicari di primary_tenant_id caller
    (WA blast adalah jemaat-specific). Data transaksi mengikuti visible_tenant_ids.

    RBAC: Bendahara / Ketua Keuangan (yang punya wewenang share laporan).
    Kalau 0 auditor ditemukan di tenant → return 400 dengan pesan jelas.
    """
    _require_role(scope, ["BENDAHARA", "KETUA_KEUANGAN"])

    primary_tenant_id = scope.primary_tenant_id
    if not primary_tenant_id:
        raise HTTPException(400, "User tidak terkait dengan tenant/jemaat")

    tenant = db.query(Tenant).filter(Tenant.id == primary_tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    # Find auditors in this tenant (selalu di primary_tenant_id caller,
    # bukan visible_tenant_ids — auditor WA-blast adalah jemaat-specific)
    auditors = (
        db.query(User)
        .filter(User.tenant_id == primary_tenant_id)
        .filter(User.role == "AUDITOR_MISI")
        .filter(User.is_active == True)  # noqa: E712
        .order_by(User.id.asc())
        .all()
    )

    if not auditors:
        raise HTTPException(
            400,
            "Tidak ada Auditor Misi terdaftar di jemaat ini. Daftarkan lewat /register/auditor dulu.",
        )

    # Load data (pakai visible_tenant_ids agar AUDITOR_MISI / ADMIN_UNI
    # bisa mengirim laporan gabungan lintas jemaat tanpa bocor keluar scope)
    kuitansi_rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Kuitansi.is_purged == False)
        .filter(Kuitansi.status == "finalized")
        .order_by(Kuitansi.nomor_kuitansi.asc())
        .all()
    )
    pengeluaran_rows = (
        db.query(Pengeluaran)
        .filter(Pengeluaran.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Pengeluaran.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Pengeluaran.is_purged == False)
        .filter(Pengeluaran.status != "draft")
        .order_by(Pengeluaran.nomor_pengeluaran.asc())
        .all()
    )

    if not kuitansi_rows and not pengeluaran_rows:
        raise HTTPException(404, "Tidak ada transaksi di rekap ini — tidak ada yang dikirim")

    kat_ids = list({p.kategori_pengeluaran_id for p in pengeluaran_rows})
    kat_map = {}
    if kat_ids:
        kats = db.query(KategoriPengeluaran).filter(KategoriPengeluaran.id.in_(kat_ids)).all()
        kat_map = {k.id: k for k in kats}

    if kuitansi_rows:
        tanggal_sabat = kuitansi_rows[0].tanggal_sabat
    else:
        tanggal_sabat = pengeluaran_rows[0].tanggal_sabat

    # Generate PDF (unique per send to avoid file locking + collision)
    pdf_dir = Path(os.path.join(os.getcwd(), "storage", "temp"))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    short_uuid = uuid.uuid4().hex[:8]
    pdf_filename = f"GABUNGAN_{id_rekap_mingguan.replace('/', '_')}_{short_uuid}.pdf"
    pdf_path = pdf_dir / pdf_filename

    try:
        generate_gabungan_pdf(
            kuitansi_list=kuitansi_rows,
            pengeluaran_list=pengeluaran_rows,
            tenant=tenant,
            id_rekap_mingguan=id_rekap_mingguan,
            tanggal_sabat_iso=str(tanggal_sabat),
            kategori_map=kat_map,
            output_path=str(pdf_path),
        )
    except Exception as exc:
        print(f"[LAPORAN-GABUNGAN-SEND] pdf error: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise HTTPException(500, f"Gagal generate PDF: {type(exc).__name__}: {str(exc)[:200]}")

    # Compute summary for caption
    total_penerimaan = sum(k.total_pemberian_angka or 0 for k in kuitansi_rows)
    total_peng_approved = sum(
        (p.jumlah or 0) for p in pengeluaran_rows if p.status == "approved"
    )
    net_saldo = total_penerimaan - total_peng_approved

    caption = (
        f"*LAPORAN GABUNGAN AUDIT*\n"
        f"GMAHK - {tenant.nama_jemaat_lokal}\n"
        f"Sabat: {tanggal_sabat} (ID: {id_rekap_mingguan})\n\n"
        f"Yth. Auditor Misi,\n\n"
        f"Laporan gabungan (Penerimaan + Pengeluaran) terlampir. Ringkasan:\n"
        f"• Total Penerimaan : Rp {total_penerimaan:,}\n"
        f"• Total Pengeluaran (Approved): Rp {total_peng_approved:,}\n"
        f"• *Net Saldo* : Rp {net_saldo:,}\n\n"
        f"*Terbilang (Net):* {terbilang(net_saldo)}\n\n"
        f"Mohon review untuk audit internal jemaat. Terima kasih.\n"
        f"--\nBendahara (FLIPUS auto-report)"
    )

    # Send to each auditor (with WA)
    notified = 0
    skipped = []
    fonnte_results = []
    for auditor in auditors:
        phone = auditor.nomor_whatsapp
        if not phone:
            skipped.append({"auditor_id": auditor.id, "reason": "no_whatsapp"})
            continue
        try:
            resp = send_document_message(
                phone=phone,
                message=caption,
                file_path=str(pdf_path),
                filename=pdf_filename,
            )
            fonnte_results.append({"auditor_id": auditor.id, "phone": phone, "response": resp})
            if isinstance(resp, dict) and resp.get("status") in ("sent", "ok"):
                notified += 1
        except Exception as exc:
            print(f"[LAPORAN-GABUNGAN-SEND] send to {phone} failed: {exc}", file=sys.stderr, flush=True)
            skipped.append({"auditor_id": auditor.id, "reason": f"fonnte_error: {str(exc)[:80]}"})

    # Audit log
    try:
        db.add(AuditLog(
            tenant_id=primary_tenant_id,
            action=(
                f"LAPORAN_GABUNGAN_SEND_TO_AUDITOR_id_rekap_{id_rekap_mingguan}"
                f"_by_user_{scope.user_id}"
                f"_auditors_{len(auditors)}_notified_{notified}_skipped_{len(skipped)}"
                f"_pdf_{pdf_filename}"
            ),
        ))
        db.commit()
    except Exception as exc:
        print(f"[LAPORAN-GABUNGAN-SEND] audit log error: {exc}", file=sys.stderr, flush=True)
        db.rollback()

    return SendToAuditorOut(
        status="ok",
        id_rekap_mingguan=id_rekap_mingguan,
        pdf_path=f"/storage/temp/{pdf_filename}",
        pdf_filename=pdf_filename,
        auditors_found=len(auditors),
        auditors_notified=notified,
        auditors_skipped=skipped,
    )