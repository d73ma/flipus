"""FLIPUS v1.1 — Reports API + WA Blast + Sabat Info."""
import logging
import traceback
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.core.tenant_scope import (
    TenantScope,
    require_tenant_scope,
)
from app.models.audit import AuditLog
from app.models.tenant import Tenant
from app.models.transaction import Kuitansi
from app.models.user import User
from app.services.notification_service import EventType, create_notification
from app.utils.nomor_kuitansi import bulan_ke_romawi
from app.utils.number_to_words import terbilang
from app.utils.sabat_counter import get_current_sabat

logger = logging.getLogger(__name__)

router = APIRouter()

class ReportItem(BaseModel):
    nomor_kuitansi: str
    perpuluhan_x_angka: int
    pt_angka: int
    total_pemberian_angka: int
    total_pemberian_huruf: str
    porsi_kantor_misi: int
    porsi_kas_jemaat: int

class ReportOut(BaseModel):
    tanggal_sabat: str
    id_rekap_mingguan: str
    items: list
    grand_total_x: int
    grand_total_pt: int
    grand_total_misi: int
    grand_total_jemaat: int
    grand_total_huruf: str

class SummaryOut(BaseModel):
    bulan: str
    nama_jemaat: str
    jumlah_kuitansi: int
    grand_total_x: int
    grand_total_pt: int
    grand_total_misi: int
    grand_total_jemaat: int
    grand_total_huruf: str

class BlastOut(BaseModel):
    status: str
    target: str
    id_rekap_mingguan: str
    grand_total: int
    pdf_path: str = None
    pdf_filename: str = None
    fonnte_response: dict

class BlastRequest(BaseModel):
    id_rekap_mingguan: str = None
    target: str = None
    target_role: str = None  # 'pendeta' | 'ketua' (lowercase, frontend-friendly)
    # v1.5-C: idempotency_key — UUID dari frontend per click. Cegah double-blast.
    idempotency_key: str | None = None

class SabatInfoOut(BaseModel):
    sabat_ke: int
    tanggal_sabat: str
    hari: str
    tahun: int
    bulan_romawi: str
    bulan_nama: str
    # Untuk Bendahara auto-generate nomor kuitansi
    next_urutan_hint: int = 1

def _require_bendahara(current_user: dict):
    if current_user["role"] not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya bendahara/ketua keuangan")

@router.get("/sabat-info", tags=['Reports'], response_model=SabatInfoOut)
def get_sabat_info_endpoint(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """
    Info Sabat untuk tanggal hari ini.

    FASE4-S6C: pakai TenantScope. next_urutan_hint dihitung dari visible tenants
    caller (own tenant untuk jemaat-scoped role, semua jemaat untuk ADMIN_UNI).

    Return:
        sabat_ke: Sabat ke-N dalam tahun (1, 2, 3, ...)
        tanggal_sabat: ISO date Sabat (YYYY-MM-DD)
        hari: "Sabtu"
        tahun: tahun Sabat
        bulan_romawi: bulan dalam angka Romawi (I, II, ..., XII)
        bulan_nama: nama bulan Indonesia
        next_urutan_hint: hint nomor urut berikutnya (existing count + 1)

    Pakai: tampilkan di pojok kanan atas BendaharaDashboard:
        "Sabat ke-32, 22 Agustus 2026"
    """
    info = get_current_sabat()
    tgl = datetime.fromisoformat(info["tanggal_sabat"])

    # Hitung hint urutan berikutnya (existing kuitansi di tanggal_sabat ini + 1)
    existing_count = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
        .filter(Kuitansi.tanggal_sabat == info["tanggal_sabat"])
        .filter(Kuitansi.is_purged == False)  # noqa: E712
        .count()
    )

    bulan_nama_id = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember",
    }

    return SabatInfoOut(
        sabat_ke=info["sabat_ke"],
        tanggal_sabat=info["tanggal_sabat"],
        hari=info["hari"],
        tahun=info["tahun"],
        bulan_romawi=bulan_ke_romawi(tgl.month),
        bulan_nama=bulan_nama_id[tgl.month],
        next_urutan_hint=existing_count + 1,
    )


@router.get("/mingguan", tags=['Reports'], response_model=ReportOut)
def laporan_mingguan(
    id_rekap_mingguan: str,
    status_filter: str = "finalized",  # T23-1: 'finalized'|'draft'|'all'
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    """Rekap per minggu/Sabat (satu id_rekap_mingguan).

    FASE4-S6C: pakai TenantScope — filter ke visible tenants caller.

    T23-1: Approval Workflow
    - status_filter='finalized' (default): hanya kuitansi yang sudah approved
    - status_filter='draft': hanya draft (untuk Bendahara lihat pending mereka)
    - status_filter='all': semua (untuk preview sebelum approval)
    """
    q = (
        db.query(Kuitansi)
        .filter(Kuitansi.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
    )
    if status_filter == "finalized":
        q = q.filter(Kuitansi.status == "finalized")
    elif status_filter == "draft":
        q = q.filter(Kuitansi.status == "draft")
    elif status_filter == "rejected":
        q = q.filter(Kuitansi.status == "rejected")
    elif status_filter == "all":
        pass  # no filter
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "status_filter harus 'finalized'|'draft'|'rejected'|'all'")
    rows = q.all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rekap tidak ditemukan")
    items = []
    sum_x = sum_pt = sum_misi = sum_jemaat = 0
    for r in rows:
        items.append(ReportItem(
            nomor_kuitansi=r.nomor_kuitansi,
            perpuluhan_x_angka=r.perpuluhan_x_angka,
            pt_angka=r.pt_angka,
            total_pemberian_angka=r.total_pemberian_angka,
            total_pemberian_huruf=r.total_pemberian_huruf,
            porsi_kantor_misi=r.porsi_kantor_misi,
            porsi_kas_jemaat=r.porsi_kas_jemaat,
        ))
        sum_x += r.perpuluhan_x_angka
        sum_pt += r.pt_angka
        sum_misi += r.porsi_kantor_misi
        sum_jemaat += r.porsi_kas_jemaat
    return ReportOut(
        tanggal_sabat=rows[0].tanggal_sabat,
        id_rekap_mingguan=id_rekap_mingguan,
        items=items,
        grand_total_x=sum_x,
        grand_total_pt=sum_pt,
        grand_total_misi=sum_misi,
        grand_total_jemaat=sum_jemaat,
        grand_total_huruf=terbilang(sum_x + sum_pt),
    )

@router.get("/summary", tags=['Reports'], response_model=SummaryOut)
def ringkasan_summary(
    bulan: str = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Dashboard ringkasan per bulan untuk Ketua Keuangan."""
    if not bulan:
        bulan = datetime.now(UTC).strftime("%Y-%m")
    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id == tenant.id)
        .filter(Kuitansi.is_purged == False)  # noqa: E712
        .all()
    )
    items = []
    sum_x = sum_pt = sum_misi = sum_jemaat = 0
    for r in rows:
        if not r.tanggal_sabat or not r.tanggal_sabat.startswith(bulan):
            continue
        items.append({
            "nomor_kuitansi": r.nomor_kuitansi,
            "perpuluhan_x_angka": r.perpuluhan_x_angka,
            "pt_angka": r.pt_angka,
            "total_pemberian_angka": r.total_pemberian_angka,
            "tanggal_sabat": r.tanggal_sabat,
        })
        sum_x += r.perpuluhan_x_angka
        sum_pt += r.pt_angka
        sum_misi += r.porsi_kantor_misi
        sum_jemaat += r.porsi_kas_jemaat
    return SummaryOut(
        bulan=bulan,
        nama_jemaat=tenant.nama_jemaat_lokal,
        jumlah_kuitansi=len(items),
        grand_total_x=sum_x,
        grand_total_pt=sum_pt,
        grand_total_misi=sum_misi,
        grand_total_jemaat=sum_jemaat,
        grand_total_huruf=terbilang(sum_x + sum_pt),
    )

@router.post("/blast-weekly", tags=['Reports'], response_model=BlastOut)
def blast_weekly(
    request: BlastRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Kirim rekap mingguan via WhatsApp ke Pendeta (atau nomor custom).
    Format: PDF attachment (aggregate only — TIDAK ada nama pemberi).

    Flow:
    1. Rekap di-load dari DB
    2. Generate PDF (header resmi, tabel kuitansi, grand total, distribusi)
    3. Save PDF ke storage/temp/<id_rekap>.pdf
    4. Kirim PDF via Fonnte (dengan caption singkat)
    5. Audit log

    v1.5-C: Idempotency — kalau request.idempotency_key sudah pernah diproses,
    return response dari BlastJob yg ada (no re-send).

    T108 (2026-08-26): Top-level try/except supaya unexpected error (mis. bug di
    create_notification) tidak return 500 generic — convert ke HTTP 500 dengan
    detail jelas. Sebelumnya Jerry screenshot "Request failed with status code 500"
    tanpa tahu akar masalah.
    """
    import traceback as _tb_t108
    try:
        return _blast_weekly_impl(request, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        tb = _tb_t108.format_exc()
        logger.exception(f"[DBG blast-500] user={current_user.get('id')} tenant={current_user.get('tenant_id')} idem={request.idempotency_key}\n{tb}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Gagal blast WA: {type(e).__name__}: {str(e)[:300]}. Cek backend log untuk traceback lengkap.",
        ) from e


def _blast_weekly_impl(request, db, current_user):
    """Inner implementation of blast_weekly — dipisah agar bisa di-wrap try/except (T108)."""
    _require_bendahara(current_user)
    id_rekap_mingguan = request.id_rekap_mingguan
    target = request.target
    target_role = (request.target_role or "").upper() or "PENDETA"
    if target_role not in ("PENDETA", "KETUA_KEUANGAN"):
        target_role = "PENDETA"

    # v1.5-C: Idempotency check
    from app.models.blast_job import BlastJob
    if request.idempotency_key:
        existing = (
            db.query(BlastJob)
            .filter(BlastJob.idempotency_key == request.idempotency_key)
            .first()
        )
        if existing:
            # Return response yg tersimpan — tidak kirim ulang
            logger.info(
                f"[WA-BLAST-IDEM] idempotency_key={request.idempotency_key} "
                f"reusing existing job id={existing.id} status={existing.status}",
            )
            return BlastOut(
                status=existing.status,
                target=existing.target_phone or "",
                id_rekap_mingguan=existing.id_rekap_mingguan,
                grand_total=0,
                pdf_path=(f"/storage/temp/{existing.pdf_filename}" if existing.pdf_filename else None),
                pdf_filename=existing.pdf_filename,
                fonnte_response=existing.fonnte_response or {"idempotent": True, "job_id": existing.id},
            )

    if not id_rekap_mingguan:
        today = datetime.now(UTC).strftime("%Y%m%d")
        id_rekap_mingguan = "RK-" + today
    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.id_rekap_mingguan == id_rekap_mingguan)
        .filter(Kuitansi.tenant_id == current_user["tenant_id"])
        .filter(Kuitansi.is_purged == False)  # noqa: E712
        .filter(Kuitansi.status == "finalized")  # T23-1: hanya approved
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rekap minggu ini belum ada (atau belum di-approve Ketua)")
    sum_x = sum(r.perpuluhan_x_angka for r in rows)
    sum_pt = sum(r.pt_angka for r in rows)
    sum_khusus = sum(r.khusus_angka for r in rows)
    sum_misi = sum(r.porsi_kantor_misi for r in rows)
    sum_jemaat = sum(r.porsi_kas_jemaat for r in rows)
    total = sum_x + sum_pt
    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    if not target:
        # Lookup target by role (T29 fix: sebelumnya hardcode "PENDETA").
        # Frontend sekarang bisa specify target_role='pendeta' atau 'ketua'.
        target_user = (
            db.query(User)
            .filter(
                User.tenant_id == current_user["tenant_id"],
                User.role == target_role,
                User.is_active == True,  # noqa: E712
            )
            .order_by(User.id.asc())
            .first()
        )
        if not target_user or not target_user.nomor_whatsapp:
            role_label = "Pendeta" if target_role == "PENDETA" else "Ketua Keuangan"
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{role_label} untuk jemaat ini belum punya nomor WhatsApp. Set di Profil Pejabat atau minta Admin Uni tambah.",
            )
        target = target_user.nomor_whatsapp

    # === Generate PDF ===
    import os as os_mod
    from pathlib import Path as Path_mod

    from app.services.pdf_generator import generate_mingguan_pdf

    pdf_dir = Path_mod(os_mod.path.join(os_mod.getcwd(), "storage", "temp"))
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"{id_rekap_mingguan.replace('/', '_')}.pdf"
    pdf_path = pdf_dir / pdf_filename

    try:
        generate_mingguan_pdf(
            kuitansi_list=rows,
            tenant=tenant,
            id_rekap_mingguan=id_rekap_mingguan,
            tanggal_sabat_iso=str(rows[0].tanggal_sabat),
            output_path=str(pdf_path),
        )
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Gagal generate PDF: {e}") from e

    # === Kirim via Fonnte (PDF attachment) ===
    khusus_line = f"• Khusus : Rp {sum_khusus:,}\n" if sum_khusus > 0 else ""
    role_salam = "Pendeta" if target_role == "PENDETA" else "Ketua Keuangan"
    caption = (
        f"*LAPORAN MINGGUAN PERPULUHAN*\n"
        f"GMAHK - {tenant.nama_jemaat_lokal}\n"
        f"Tanggal Sabat: {rows[0].tanggal_sabat}\n\n"
        f"Salam {role_salam},\n\n"
        f"Laporan lengkap dalam lampiran PDF. Ringkasan:\n"
        f"• Perpuluhan (X) : Rp {sum_x:,}\n"
        f"• Persembahan (PT): Rp {sum_pt:,}\n"
        f"{khusus_line}"
        f"• *Total* : Rp {total:,}\n\n"
        f"*Penyaluran:*\n"
        f"• Kantor Misi : Rp {sum_misi:,}\n"
        f"• Kas Jemaat : Rp {sum_jemaat:,}\n\n"
        f"*Terbilang:* {terbilang(total)}\n\n"
        f"Semoga Tuhan memberkati pelayanan jemaat.\n"
        f"--\nBendahara (FLIPUS auto-report)"
    )

    from app.services.whatsapp import send_document_message

    # v1.5-C: Create BlastJob record (pending) sebelum kirim.
    # Kalau ada exception saat generate/kirim, kita update record di finally.
    blast_job = None
    if request.idempotency_key:
        from datetime import datetime as _dt
        blast_job = BlastJob(
            tenant_id=current_user["tenant_id"],
            user_id=current_user["id"],
            idempotency_key=request.idempotency_key,
            id_rekap_mingguan=id_rekap_mingguan,
            status="pending",
            target_phone=target,
        )
        db.add(blast_job)
        try:
            db.commit()
            db.refresh(blast_job)
        except Exception as e:
            logger.exception(f"[WA-BLAST-IDEM] failed to create job: {e}")
            db.rollback()
            blast_job = None

    fonnte_resp = send_document_message(
        phone=target,
        message=caption,
        file_path=str(pdf_path),
        filename=pdf_filename,
    )

    # v1.5-C: Update BlastJob dengan hasil
    if blast_job is not None:
        from datetime import datetime as _dt
        blast_job.pdf_filename = pdf_filename
        blast_job.fonnte_response = fonnte_resp if isinstance(fonnte_resp, dict) else {"raw": str(fonnte_resp)}
        blast_job.status = "sent" if (
            isinstance(fonnte_resp, dict) and (
                fonnte_resp.get("status") in ("sent", "ok")
                or fonnte_resp.get("detail") in ("sent", "ok")
            )
        ) else "failed"
        blast_job.completed_at = _dt.now(UTC)
        try:
            db.commit()
        except Exception as e:
            logger.exception(f"[WA-BLAST-IDEM] failed to update job: {e}")
            db.rollback()

    # Log blast attempt (visible di uvicorn stderr)
    logger.error( f"[WA-BLAST] target_role={target_role} phone={target} " f"status={fonnte_resp.get('status') if isinstance(fonnte_resp, dict) else 'unknown'} " f"reason={fonnte_resp.get('reason', '-') if isinstance(fonnte_resp, dict) else '-'}" )

    audit = AuditLog(
        tenant_id=current_user["tenant_id"],
        action="WA_BLAST_PDF_user_" + str(current_user["id"]) + "_rk_" + id_rekap_mingguan,
        payload_hash=id_rekap_mingguan,
        porsi_dana_misi=sum_misi,
    )
    db.add(audit)
    db.commit()

    # T24: Notify Pendeta + Ketua when weekly blast completes
    blast_success = isinstance(fonnte_resp, dict) and (
        fonnte_resp.get("status") in ("sent", "ok") or fonnte_resp.get("detail") in ("sent", "ok")
    )

    # Fail-fast: kalau WA gagal kirim, raise HTTP 502 biar frontend tidak fallback ke generic.
    # PDF sudah ter-generate (di /storage/temp) — caller bisa download manual via /v1/reports/mingguan.
    if not blast_success:
        reason = (
            fonnte_resp.get("reason") if isinstance(fonnte_resp, dict) else None
        ) or (
            fonnte_resp.get("fonnte_response", {}).get("reason")
            if isinstance(fonnte_resp, dict) else None
        ) or "Fonnte reply tanpa status=true"
        # Lookup nama target untuk message jelas
        target_name = target
        try:
            u = db.query(User).filter(User.nomor_whatsapp == target).first()
            if u:
                target_name = f"{u.nama_lengkap} ({target})"
        except Exception:
            logger.exception("lookup target_name gagal")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Gagal kirim WA ke {target_name}. Alasan: {reason}. "
            f"PDF sudah ter-generate di storage/temp/{pdf_filename} — bisa di-download manual.",
        )

    # Notify Pendeta (lookup per-tenant, T29 fix)
    pendeta_user = (
        db.query(User)
        .filter(User.tenant_id == current_user["tenant_id"], User.role == "PENDETA", User.is_active == True)  # noqa: E712  # noqa: E712
        .order_by(User.id.asc())
        .first()
    )
    if pendeta_user and pendeta_user.id != current_user["id"]:
        create_notification(
            db,
            user_id=pendeta_user.id,
            tenant_id=pendeta_user.tenant_id or current_user["tenant_id"],
            event_type=EventType.WEEKLY_BLAST_DONE,
            title="Laporan mingguan terkirim",
            message=(
                f"Laporan perpuluhan minggu {id_rekap_mingguan} (total Rp {total:,}) "
                f"telah dikirim via WhatsApp ke {target}."
            ),
            link="/pendeta",
            related_entity_type="rekap",
            related_entity_id=id_rekap_mingguan,
            extra_data={
                "id_rekap_mingguan": id_rekap_mingguan,
                "total": total,
                "wa_target": target,
                "wa_status": "sent" if blast_success else "failed",
            },
            actor_user_id=current_user["id"],
            commit=False,
        )

    # Notify Ketua Keuangan di jemaat yang sama
    ketua = (
        db.query(User)
        .filter(
            User.tenant_id == current_user["tenant_id"],
            User.role == "KETUA_KEUANGAN",
            User.is_active == True,  # noqa: E712
        )
        .first()
    )
    if ketua and ketua.id != current_user["id"]:
        create_notification(
            db,
            user_id=ketua.id,
            tenant_id=ketua.tenant_id,
            event_type=EventType.WEEKLY_BLAST_DONE,
            title="Blast mingguan selesai",
            message=(
                f"Bendahara telah mengirim laporan mingguan {id_rekap_mingguan} (Rp {total:,}) "
                f"via WhatsApp."
            ),
            link="/ketua",
            related_entity_type="rekap",
            related_entity_id=id_rekap_mingguan,
            actor_user_id=current_user["id"],
            commit=False,
        )

    db.commit()

    return BlastOut(
        status="ok",
        target=target,
        id_rekap_mingguan=id_rekap_mingguan,
        grand_total=total,
        pdf_path=str(pdf_path),
        pdf_filename=pdf_filename,
        fonnte_response=fonnte_resp if isinstance(fonnte_resp, dict) else {"raw": str(fonnte_resp)},
    )


# ===== T36 Redesign: Laporan Keuangan (sabat range) + auto-blast =====

class LaporanKeuanganRequest(BaseModel):
    """Request body untuk generate laporan keuangan rentang sabat."""
    sabat_from: int  # sabat ke-N dalam tahun (misal 28)
    sabat_to: int    # sabat ke-M (misal 34, harus >= sabat_from)
    tahun: int = None  # default: tahun sabat berjalan
    blast_targets: list[str] = ["PENDETA", "KETUA_KEUANGAN"]  # role target auto-blast
    sanitize_nama_for_ketua: bool = True  # T36: Ketua dapat versi tanpa nama


class LaporanKeuanganOut(BaseModel):
    sabat_from: int
    sabat_to: int
    tahun: int
    jumlah_kuitansi: int
    grand_total_x: int
    grand_total_pt: int
    grand_total_khusus: int
    grand_total_porsi_misi: int
    grand_total_porsi_jemaat: int
    grand_total_huruf: str
    pdf_filename: str
    pdf_size_bytes: int
    pdf_url: str
    blast_results: list[dict] = []


def _sabat_ke_to_date_range(tahun: int, sabat_from: int, sabat_to: int) -> tuple[str, str]:
    """
    Convert (tahun, sabat_from, sabat_to) ke (date_from, date_to) ISO string.

    Sabtu pertama tahun: cari Sabtu pertama di tahun tersebut.
    sabat ke-N = Sabtu pertama + (N-1) * 7 hari.
    """
    from datetime import timedelta
    year_start = datetime(tahun, 1, 1)
    days_to_first_saturday = (5 - year_start.weekday()) % 7
    first_saturday = year_start + timedelta(days=days_to_first_saturday)
    date_from = (first_saturday + timedelta(days=(sabat_from - 1) * 7)).date()
    date_to = (first_saturday + timedelta(days=(sabat_to - 1) * 7)).date()
    return date_from.isoformat(), date_to.isoformat()


@router.post("/keuangan", tags=['Reports'], response_model=LaporanKeuanganOut)
def generate_laporan_keuangan(
    payload: LaporanKeuanganRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    T36 Redesign: Laporan Keuangan untuk rapat jemaat.

    Pilih rentang sabat (dari sabat ke-N sampai ke-M dalam tahun).
    Hasilnya:
    1. Aggregate kuitansi finalized dalam range
    2. Generate PDF (header resmi + tabel aggregate)
    3. Auto-blast ke Pendeta (full data) + Ketua (sanitize nama jika di-set)
    4. Save PDF di /storage/laporan/<tenant_id>/<filename>
    5. Return URL PDF untuk di-download

    RBAC: BENDAHARA / KETUA_KEUANGAN only.
    """
    try:
        return _generate_laporan_keuangan_impl(payload, db, current_user, logger)
    except HTTPException:
        # Biarkan HTTPException pass-through (sudah benar format)
        raise
    except Exception as e:
        # Catch-all: convert unexpected error jadi HTTP 500 dengan detail jelas
        tb = traceback.format_exc()
        logger.error(f"[laporan] UNEXPECTED ERROR: {e}\n{tb}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Gagal generate laporan: {type(e).__name__}: {e}",
        ) from e


def _generate_laporan_keuangan_impl(payload, db, current_user, logger):
    """Inner implementation — semua logic, di-wrap try/except di outer function."""
    # T107 DEBUG (2026-08-26): log role sebelum validasi untuk diagnosa error
    logger.error(f"[DBG laporan] role={current_user['role']!r} id={current_user.get('id')} tenant_id={current_user.get('tenant_id')}")
    if current_user["role"] not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Bendahara/Ketua Keuangan")

    if payload.sabat_from > payload.sabat_to:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sabat_from harus <= sabat_to")
    if payload.sabat_from < 1 or payload.sabat_to > 54:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sabat harus dalam range 1-54")

    tahun = payload.tahun or datetime.now().year
    date_from, date_to = _sabat_ke_to_date_range(tahun, payload.sabat_from, payload.sabat_to)

    # Aggregate kuitansi
    rows = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id == current_user["tenant_id"])
        .filter(Kuitansi.is_purged == False)  # noqa: E712  # noqa: E712
        .filter(Kuitansi.status == "finalized")
        .filter(Kuitansi.tanggal_sabat >= date_from)
        .filter(Kuitansi.tanggal_sabat <= date_to)
        .order_by(Kuitansi.tanggal_sabat.asc(), Kuitansi.nomor_kuitansi.asc())
        .all()
    )

    if not rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Tidak ada kuitansi finalized antara Sabat ke-{payload.sabat_from} sampai ke-{payload.sabat_to} tahun {tahun}",
        )

    sum_x = sum(r.perpuluhan_x_angka for r in rows)
    sum_pt = sum(r.pt_angka for r in rows)
    sum_kh = sum(r.khusus_angka for r in rows)
    sum_misi = sum(r.porsi_kantor_misi for r in rows)
    sum_jemaat = sum(r.porsi_kas_jemaat for r in rows)
    total = sum_x + sum_pt + sum_kh

    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant tidak ditemukan")

    # === Generate PDF ===
    import os as os_mod
    from pathlib import Path as Path_mod

    from app.services.pdf_generator import generate_mingguan_pdf

    # Folder: storage/laporan/<tenant_id>/
    pdf_dir = Path_mod(os_mod.path.join(os_mod.getcwd(), "storage", "laporan", str(tenant.id)))
    pdf_dir.mkdir(parents=True, exist_ok=True)

    pdf_filename = f"laporan_keuangan_{tahun}_S{payload.sabat_from:02d}-S{payload.sabat_to:02d}.pdf"
    pdf_path = pdf_dir / pdf_filename

    # ID rekap: gabungan range
    id_rekap_range = f"LK-{tahun}-S{payload.sabat_from:02d}-S{payload.sabat_to:02d}"
    tanggal_range = f"{date_from} s/d {date_to}"

    try:
        generate_mingguan_pdf(
            kuitansi_list=rows,
            tenant=tenant,
            id_rekap_mingguan=id_rekap_range,
            tanggal_sabat_iso=tanggal_range,
            output_path=str(pdf_path),
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Gagal generate PDF: {type(e).__name__}: {e}",
        ) from e

    pdf_size = os_mod.path.getsize(pdf_path)
    pdf_url = f"/storage/laporan/{tenant.id}/{pdf_filename}"

    # === Auto-blast ===
    blast_results: list[dict] = []
    from app.services.whatsapp import send_document_message

    for target_role in payload.blast_targets:
        if target_role not in ("PENDETA", "KETUA_KEUANGAN"):
            continue
        target_user = (
            db.query(User)
            .filter(
                User.tenant_id == current_user["tenant_id"],
                User.role == target_role,
                User.is_active == True,  # noqa: E712
            )
            .order_by(User.id.asc())
            .first()
        )
        if not target_user or not target_user.nomor_whatsapp:
            blast_results.append({
                "role": target_role,
                "status": "skipped",
                "reason": f"Tidak ada user aktif dengan nomor WhatsApp untuk role {target_role}",
            })
            continue

        # Sanitize nama untuk Ketua (aggregate only, tanpa nama pemberi)
        # generate_mingguan_pdf sudah aggregate only (tanpa nama), jadi default aman
        # Opsi sanitize_nama_for_ketua: kalau True dan target=Ketua, gunakan versi aggregate
        # (saat ini generate_mingguan_pdf sudah aggregate, jadi flag hanya marker)
        caption = (
            f"*LAPORAN KEUANGAN JEMAAT*\n"
            f"GMAHK - {tenant.nama_jemaat_lokal}\n"
            f"Periode: Sabat ke-{payload.sabat_from} s/d Sabat ke-{payload.sabat_to} "
            f"({date_from} s/d {date_to})\n\n"
            f"Salam {target_role.title()},\n\n"
            f"Laporan keuangan lengkap dalam lampiran PDF. Ringkasan:\n"
            f"• Perpuluhan (X)    : Rp {sum_x:,}\n"
            f"• Persembahan (PT) : Rp {sum_pt:,}\n"
            f"• Khusus            : Rp {sum_kh:,}\n"
            f"• *Total*          : Rp {total:,}\n\n"
            f"*Penyaluran:*\n"
            f"• Kantor Misi  : Rp {sum_misi:,}\n"
            f"• Kas Jemaat    : Rp {sum_jemaat:,}\n\n"
            f"*Terbilang:* {terbilang(total)}\n\n"
        )
        if target_role == "KETUA_KEUANGAN" and payload.sanitize_nama_for_ketua:
            caption += "(Laporan versi aggregate — tanpa nama pemberi perorangan)\n\n"
        caption += (
            "Laporan ini disiapkan untuk rapat jemaat. Silakan review dan gunakan "
            "untuk dokumentasi resmi.\n\n"
            "--\nBendahara (FLIPUS auto-report)"
        )

        try:
            fonnte_resp = send_document_message(
                phone=target_user.nomor_whatsapp,
                message=caption,
                file_path=str(pdf_path),
                filename=pdf_filename,
            )
            success = isinstance(fonnte_resp, dict) and (
                fonnte_resp.get("status") in ("sent", "ok") or fonnte_resp.get("detail") in ("sent", "ok")
            )
            blast_results.append({
                "role": target_role,
                "user_id": target_user.id,
                "nama": target_user.nama_lengkap,
                "phone": target_user.nomor_whatsapp,
                "status": "sent" if success else "failed",
                "response": fonnte_resp if isinstance(fonnte_resp, dict) else {"raw": str(fonnte_resp)},
            })
        except Exception as e:
            # T107 (2026-08-26): log detail agar diagnosable dari frontend
            tb = traceback.format_exc()
            logger.exception(f"[DBG blast-FAIL role={target_role}] {type(e).__name__}: {e}\n{tb}")
            blast_results.append({
                "role": target_role,
                "user_id": target_user.id,
                "nama": target_user.nama_lengkap,
                "phone": target_user.nomor_whatsapp,
                "status": "failed",
                "reason": f"{type(e).__name__}: {str(e)[:200]}",
            })

    # === Audit log ===
    audit = AuditLog(
        tenant_id=current_user["tenant_id"],
        action="LAPORAN_KEUANGAN_user_" + str(current_user["id"]) + "_" + id_rekap_range,
        payload_hash=id_rekap_range,
        porsi_dana_misi=sum_misi,
    )
    db.add(audit)
    db.commit()

    return LaporanKeuanganOut(
        sabat_from=payload.sabat_from,
        sabat_to=payload.sabat_to,
        tahun=tahun,
        jumlah_kuitansi=len(rows),
        grand_total_x=sum_x,
        grand_total_pt=sum_pt,
        grand_total_khusus=sum_kh,
        grand_total_porsi_misi=sum_misi,
        grand_total_porsi_jemaat=sum_jemaat,
        grand_total_huruf=terbilang(total),
        pdf_filename=pdf_filename,
        pdf_size_bytes=pdf_size,
        pdf_url=pdf_url,
        blast_results=blast_results,
    )
