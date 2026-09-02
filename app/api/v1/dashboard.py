"""
FLIPUS v1.1 — Dashboard helper endpoints + Kuitansi submit.

Endpoint:
- GET /sabat-info — info Sabat hari ini
- POST /kuitansi — Bendahara create kuitansi (manual / batch save OCR result)
              + auto-thanks WA kalau ada nomor (non-blocking)
"""

from datetime import datetime
from app.core.security import utcnow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import encrypt_pii, decrypt_pii
from app.api.v1.auth import get_current_user
from app.utils.sabat_counter import get_current_sabat, get_sabat_info, get_effective_sabat_for_input
from app.utils.nomor_kuitansi import generate_nomor_kuitansi, generate_id_rekap_mingguan
from app.utils.number_to_words import terbilang
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.audit import AuditLog
from app.models.master import PersentaseConfig
from app.services.notification_service import create_notification, EventType

router = APIRouter()


class SabatInfoOut(BaseModel):
    sabat_ke: int
    tanggal_sabat: str
    hari: str
    tahun: int


@router.get("/sabat-info", response_model=SabatInfoOut)
def sabat_info(
    date: str = None,
    current_user: dict = Depends(get_current_user),
):
    """Info Sabat (Sabat ke-N, tanggal) untuk tanggal hari ini atau tertentu."""
    if date:
        try:
            tgl = datetime.fromisoformat(date)
        except ValueError:
            return get_current_sabat()
        return get_sabat_info(tgl)
    return get_current_sabat()


# ===== Kuitansi Submit =====

class KuitansiIn(BaseModel):
    """Schema untuk Bendahara create kuitansi (manual atau dari OCR)."""
    nama_umat: Optional[str] = Field(None, description="Nama pemberi (optional, akan dienkripsi)")
    nomor_whatsapp: Optional[str] = Field(None, description="WA pemberi (optional, akan dienkripsi + auto-thanks)")
    perpuluhan_x_angka: int = Field(default=0, ge=0)
    pt_angka: int = Field(default=0, ge=0)
    khusus_angka: int = Field(default=0, ge=0)
    tanggal_sabat: Optional[str] = Field(None, description="ISO date, default = sabat-info terbaru")
    id_rekap_mingguan: Optional[str] = Field(None, description="default auto-generated")
    foto_amplop_path: Optional[str] = None


class KuitansiOut(BaseModel):
    id: int
    nomor_kuitansi: str
    tanggal_sabat: str
    id_rekap_mingguan: str
    perpuluhan_x_angka: int
    pt_angka: int
    khusus_angka: int
    total_pemberian_angka: int
    total_pemberian_huruf: str
    porsi_kantor_misi: int
    porsi_kas_jemaat: int
    porsi_khusus_misi: int
    porsi_khusus_jemaat: int
    # T23-1: Approval fields
    status: str = "finalized"
    needs_approval: bool = False  # True kalau draft, butuh Ketua approval
    auto_thanks_sent: bool = False
    auto_thanks_target: Optional[str] = None


def _get_persentase_for_tenant(db: Session, tenant: Tenant) -> dict:
    """Ambil PersentaseConfig (MISI) untuk tenant ini. Default fallback."""
    if tenant.misi_konferens_id is None:
        # Tenant placeholder (admin/auditor), no config
        return {
            "pct_x_jemaat": 1.0,
            "pct_pt_jemaat": 0.5,
            "pct_khusus_jemaat": 0.0,
        }
    cfg = (
        db.query(PersentaseConfig)
        .filter(PersentaseConfig.scope == "MISI")
        .filter(PersentaseConfig.ref_id == tenant.misi_konferens_id)
        .first()
    )
    if cfg:
        return {
            "pct_x_jemaat": cfg.pct_x_jemaat,
            "pct_pt_jemaat": cfg.pct_pt_jemaat,
            "pct_khusus_jemaat": cfg.pct_khusus_jemaat,
        }
    return {"pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.0}


@router.post("/kuitansi", response_model=KuitansiOut)
def create_kuitansi(
    payload: KuitansiIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Bendahara/Ketua create kuitansi baru.

    T23-1: Approval Workflow
    - BENDAHARA → status='draft' (menunggu approval Ketua Keuangan)
    - KETUA_KEUANGAN → status='finalized' langsung (mereka punya authority)

    Flow:
    1. Validasi role (BENDAHARA/KETUA_KEUANGAN)
    2. Generate id_rekap & nomor_kuitansi otomatis (kalau tidak di-supply)
    3. Hitung porsi via PersentaseConfig (Auditor Misi)
    4. Save Kuitansi (PII encrypted, status=role-based)
    5. Kalau status='finalized' DAN ada nomor_whatsapp → kirim auto-thanks via Fonnte
       (non-blocking — kalau WA gagal, kuitansi tetap saved)
    6. Audit log
    """
    if current_user["role"] not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya bendahara/ketua keuangan")

    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    # T23-1: Determine status berdasarkan role
    initial_status = "draft" if current_user["role"] == "BENDAHARA" else "finalized"

    # Determine tanggal_sabat (T111: rule Jerry — input post-Sabat → sabat terakhir)
    if payload.tanggal_sabat:
        tanggal_sabat = payload.tanggal_sabat
    else:
        sabat_info = get_effective_sabat_for_input()
        tanggal_sabat = sabat_info["tanggal_sabat"]

    # Determine id_rekap
    id_rekap = payload.id_rekap_mingguan or generate_id_rekap_mingguan()

    # Generate nomor urut (sequence per bulan, format 001/NT/I/27)
    existing_count = (
        db.query(Kuitansi)
        .filter(Kuitansi.tenant_id == tenant.id)
        .filter(Kuitansi.tanggal_sabat == tanggal_sabat)
        .filter(Kuitansi.is_purged == False)
        .count()
    )
    urutan = existing_count + 1
    try:
        nomor_kuitansi = generate_nomor_kuitansi(
            urutan=urutan,
            initial_jemaat=tenant.initial_jemaat or "XX",
            tanggal=datetime.fromisoformat(tanggal_sabat),
        )
    except Exception:
        # Fallback kalau format gagal
        nomor_kuitansi = f"KPT-{utcnow().strftime('%Y%m%d%H%M%S')}-{urutan}"

    # Hitung porsi — FASE 2 S2/R1: pakai Jerry Model B (compute_porsi)
    # Single source of truth — semua call site harus pakai fungsi ini.
    pct = _get_persentase_for_tenant(db, tenant)
    total_x = payload.perpuluhan_x_angka
    total_pt = payload.pt_angka
    total_khusus = payload.khusus_angka
    total_pemberian = total_x + total_pt + total_khusus

    from app.utils.porsi_calculator import compute_porsi

    _porsi = compute_porsi(
        x=total_x,
        pt=total_pt,
        kh=total_khusus,
        pct_x_jemaat=pct["pct_x_jemaat"],
        pct_pt_jemaat=pct["pct_pt_jemaat"],
        pct_khusus_jemaat=pct["pct_khusus_jemaat"],
        pct_x_uni=pct["pct_x_uni"],
        pct_pt_uni=pct["pct_pt_uni"],
        pct_khusus_uni=pct["pct_khusus_uni"],
    )

    # Field yang disimpan di Kuitansi (4 kolom existing):
    #   porsi_kantor_misi  = total ke Misi (X + PT + KH ke Misi)
    #   porsi_kas_jemaat   = total ke Jemaat (X + PT + KH ke Jemaat)
    #   porsi_khusus_misi  = porsi KH yg ke Misi
    #   porsi_khusus_jemaat= porsi KH yg ke Jemaat
    porsi_kantor_misi = _porsi["pm_x"] + _porsi["pm_pt"] + _porsi["pm_kh"]
    porsi_kas_jemaat = _porsi["pj_x"] + _porsi["pj_pt"] + _porsi["pj_kh"]
    porsi_khusus_misi = _porsi["pm_kh"]
    porsi_khusus_jemaat = _porsi["pj_kh"]
    # porsi_uni tidak disimpan di model Kuitansi existing — FASE 2 S5/R4 akan tambah kolom
    porsi_x_uni = _porsi["pu_x"]
    porsi_pt_uni = _porsi["pu_pt"]
    porsi_khusus_uni = _porsi["pu_kh"]

    # Encrypt PII
    nama_encrypted = encrypt_pii(payload.nama_umat) if payload.nama_umat else None
    wa_encrypted = encrypt_pii(payload.nomor_whatsapp) if payload.nomor_whatsapp else None

    # Create Kuitansi
    k = Kuitansi(
        tenant_id=tenant.id,
        id_rekap_mingguan=id_rekap,
        nomor_kuitansi=nomor_kuitansi,
        tanggal_sabat=tanggal_sabat,
        nama_umat_encrypted=nama_encrypted,
        nomor_whatsapp_encrypted=wa_encrypted,
        foto_amplop_path=payload.foto_amplop_path,
        perpuluhan_x_angka=total_x,
        pt_angka=total_pt,
        khusus_angka=total_khusus,
        total_pemberian_angka=total_pemberian,
        total_pemberian_huruf=terbilang(total_pemberian),
        porsi_kantor_misi=porsi_kantor_misi,
        porsi_kas_jemaat=porsi_kas_jemaat,
        porsi_khusus_misi=porsi_khusus_misi,
        porsi_khusus_jemaat=porsi_khusus_jemaat,
        # T23-1: Approval workflow
        status=initial_status,
        created_by_user_id=current_user["id"],
    )
    db.add(k)
    db.flush()
    db.commit()
    db.refresh(k)

    # T23-1: Auto-thanks WA HANYA untuk kuitansi yang sudah finalized
    # (draft belum eligible untuk kirim ke umat)
    auto_thanks_sent = False
    if initial_status == "finalized" and payload.nomor_whatsapp:
        from app.services.whatsapp import send_auto_thanks
        try:
            resp = send_auto_thanks(
                phone=payload.nomor_whatsapp,
                nama=payload.nama_umat or "Saudara",
                nama_jemaat=tenant.nama_jemaat_lokal,
                tanggal_sabat=tanggal_sabat,
                perpuluhan_x=total_x,
                pt=total_pt,
                khusus=total_khusus,
                nama_pendeta=tenant.nama_pendeta or "Pendeta",
                nama_bendahara=tenant.nama_bendahara or "Bendahara",
            )
            auto_thanks_sent = isinstance(resp, dict) and resp.get("status") == "sent"
        except Exception:
            # Silent fail — audit log only
            pass

    # Audit log
    db.add(AuditLog(
        tenant_id=tenant.id,
        action=f"KUITANSI_CREATE_user_{current_user['id']}_nomor_{nomor_kuitansi}_status_{initial_status}",
        payload_hash=nomor_kuitansi,
        porsi_dana_misi=porsi_kantor_misi,
    ))
    db.commit()

    # T24: Notification trigger — notify Ketua Keuangan when Bendahara creates draft
    if initial_status == "draft":
        # Cari Ketua Keuangan di jemaat yang sama (single-user, lookup by role)
        from app.models.user import User
        ketua = (
            db.query(User)
            .filter(User.tenant_id == tenant.id, User.role == "KETUA_KEUANGAN", User.is_active == True)  # noqa: E712
            .first()
        )
        if ketua and ketua.id != current_user["id"]:
            create_notification(
                db,
                user_id=ketua.id,
                tenant_id=tenant.id,
                event_type=EventType.KUITANSI_DRAFT_CREATED,
                title=f"Kuitansi baru menunggu approval",
                message=f"Bendahara membuat draft kuitansi {nomor_kuitansi} (Rp {total_pemberian:,}) untuk {tanggal_sabat}",
                link="/ketua",
                related_entity_type="kuitansi",
                related_entity_id=str(k.id),
                extra_data={
                    "nomor_kuitansi": nomor_kuitansi,
                    "total_pemberian": total_pemberian,
                    "tanggal_sabat": tanggal_sabat,
                    "created_by_user_id": current_user["id"],
                },
                actor_user_id=current_user["id"],
                commit=False,
            )
            db.commit()

    return KuitansiOut(
        id=k.id,
        nomor_kuitansi=k.nomor_kuitansi,
        tanggal_sabat=k.tanggal_sabat,
        id_rekap_mingguan=k.id_rekap_mingguan,
        perpuluhan_x_angka=k.perpuluhan_x_angka,
        pt_angka=k.pt_angka,
        khusus_angka=k.khusus_angka,
        total_pemberian_angka=k.total_pemberian_angka,
        total_pemberian_huruf=k.total_pemberian_huruf,
        porsi_kantor_misi=k.porsi_kantor_misi,
        porsi_kas_jemaat=k.porsi_kas_jemaat,
        porsi_khusus_misi=k.porsi_khusus_misi,
        porsi_khusus_jemaat=k.porsi_khusus_jemaat,
        status=k.status,
        needs_approval=(k.status == "draft"),
        auto_thanks_sent=auto_thanks_sent,
        auto_thanks_target=payload.nomor_whatsapp if auto_thanks_sent else None,
    )


# ===== T23-2: Approval Endpoints =====

class ApprovalActionIn(BaseModel):
    """Schema untuk approve/reject."""
    reason: Optional[str] = Field(None, max_length=500, description="Required untuk reject")


class KuitansiApprovalOut(BaseModel):
    id: int
    nomor_kuitansi: str
    status: str
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[str] = None
    rejected_by_user_id: Optional[int] = None
    rejected_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    created_by_user_id: Optional[int] = None
    total_pemberian_angka: int
    tanggal_sabat: str


class PendingListOut(BaseModel):
    items: list[KuitansiApprovalOut]
    total: int


@router.post("/kuitansi/{kuitansi_id}/approve", response_model=KuitansiApprovalOut)
def approve_kuitansi(
    kuitansi_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Ketua Keuangan approve kuitansi draft.

    - Hanya KETUA_KEUANGAN yang bisa approve (atau ADMIN_UNI)
    - Hanya kuitansi dengan status='draft' yang eligible
    - Setelah approve → status='finalized'
    - Side effect: kirim auto-thanks WA kalau ada nomor WA (non-blocking)
    - Audit log
    """
    if current_user["role"] not in ("KETUA_KEUANGAN", "ADMIN_UNI"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Ketua Keuangan atau Admin Uni")

    k = db.query(Kuitansi).filter(Kuitansi.id == kuitansi_id).first()
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kuitansi tidak ditemukan")

    # Cross-tenant: pastikan caller bisa akses kuitansi ini
    caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not caller_tenant:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant not found")

    if current_user["role"] == "KETUA_KEUANGAN":
        # Ketua Keuangan: hanya tenant sendiri
        if k.tenant_id != caller_tenant.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kuitansi bukan dari jemaat Anda")
    elif current_user["role"] == "ADMIN_UNI":
        # Admin Uni: hanya uni sendiri
        k_tenant = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
        if not k_tenant or k_tenant.nama_uni != caller_tenant.nama_uni:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kuitansi bukan dari uni Anda")

    # Hanya draft yang eligible
    if k.status != "draft":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Kuitansi berstatus '{k.status}' tidak bisa di-approve (harus 'draft')",
        )

    # Approve
    k.status = "finalized"
    k.approved_by_user_id = current_user["id"]
    k.approved_at = utcnow()
    db.commit()
    db.refresh(k)

    # Side effect: auto-thanks WA (kalau eligible)
    if k.nomor_whatsapp_encrypted:
        try:
            wa = decrypt_pii(k.nomor_whatsapp_encrypted)
            nama = decrypt_pii(k.nama_umat_encrypted) if k.nama_umat_encrypted else "Saudara"
            from app.services.whatsapp import send_auto_thanks
            send_auto_thanks(
                phone=wa,
                nama=nama,
                nama_jemaat=caller_tenant.nama_jemaat_lokal,
                tanggal_sabat=k.tanggal_sabat,
                perpuluhan_x=k.perpuluhan_x_angka,
                pt=k.pt_angka,
                khusus=k.khusus_angka,
                nama_pendeta=caller_tenant.nama_pendeta or "Pendeta",
                nama_bendahara=caller_tenant.nama_bendahara or "Bendahara",
            )
        except Exception:
            # Silent fail — audit log only
            pass

    # Audit log
    db.add(AuditLog(
        tenant_id=k.tenant_id,
        action=f"KUITANSI_APPROVE_kuitansi_{k.id}_user_{current_user['id']}_from_draft_to_finalized",
        payload_hash=k.nomor_kuitansi,
    ))
    db.commit()

    # T24: Notify Bendahara (kuitansi creator) when Ketua approves
    if k.created_by_user_id and k.created_by_user_id != current_user["id"]:
        create_notification(
            db,
            user_id=k.created_by_user_id,
            tenant_id=k.tenant_id,
            event_type=EventType.KUITANSI_APPROVED,
            title="Kuitansi Anda disetujui",
            message=f"Kuitansi {k.nomor_kuitansi} (Rp {k.total_pemberian_angka:,}) telah disetujui dan siap untuk PDF/WA blast.",
            link="/bendahara",
            related_entity_type="kuitansi",
            related_entity_id=str(k.id),
            extra_data={
                "nomor_kuitansi": k.nomor_kuitansi,
                "approved_by_user_id": current_user["id"],
            },
            actor_user_id=current_user["id"],
            commit=False,
        )
        # Also notify all ADMIN_UNI in the same uni
        from app.models.user import User
        from app.models.master import Uni, MisiKonferens
        k_tenant_for_admin = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
        if k_tenant_for_admin and k_tenant_for_admin.nama_uni:
            uni = db.query(Uni).filter(Uni.nama_resmi == k_tenant_for_admin.nama_uni).first()
            if uni:
                misi_ids = [m.id for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == uni.id).all()]
                tenant_ids = [t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id.in_(misi_ids)).all()]
                admins = (
                    db.query(User)
                    .filter(User.tenant_id.in_(tenant_ids), User.role == "ADMIN_UNI", User.is_active == True)  # noqa: E712
                    .all()
                )
                for admin in admins:
                    create_notification(
                        db,
                        user_id=admin.id,
                        tenant_id=admin.tenant_id,
                        event_type=EventType.KUITANSI_APPROVED,
                        title="Kuitansi disetujui di uni Anda",
                        message=f"Kuitansi {k.nomor_kuitansi} (Rp {k.total_pemberian_angka:,}) disetujui di jemaat {k_tenant_for_admin.nama_jemaat_lokal}.",
                        link="/admin",
                        related_entity_type="kuitansi",
                        related_entity_id=str(k.id),
                        actor_user_id=current_user["id"],
                        commit=False,
                    )
        db.commit()

    return KuitansiApprovalOut(
        id=k.id,
        nomor_kuitansi=k.nomor_kuitansi,
        status=k.status,
        approved_by_user_id=k.approved_by_user_id,
        approved_at=k.approved_at.isoformat() if k.approved_at else None,
        rejected_by_user_id=k.rejected_by_user_id,
        rejected_at=k.rejected_at.isoformat() if k.rejected_at else None,
        rejected_reason=k.rejected_reason,
        created_by_user_id=k.created_by_user_id,
        total_pemberian_angka=k.total_pemberian_angka,
        tanggal_sabat=k.tanggal_sabat,
    )


@router.post("/kuitansi/{kuitansi_id}/reject", response_model=KuitansiApprovalOut)
def reject_kuitansi(
    kuitansi_id: int,
    payload: ApprovalActionIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Ketua Keuangan reject kuitansi draft dengan alasan.

    - Hanya KETUA_KEUANGAN / ADMIN_UNI
    - Hanya kuitansi status='draft'
    - Reason WAJIB (minimal 5 karakter)
    - Status berubah ke 'rejected'
    - Bendahara bisa lihat reason & koreksi (lalu create ulang)
    """
    if current_user["role"] not in ("KETUA_KEUANGAN", "ADMIN_UNI"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Ketua Keuangan atau Admin Uni")

    if not payload.reason or len(payload.reason.strip()) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Alasan reject wajib (minimal 5 karakter)")

    k = db.query(Kuitansi).filter(Kuitansi.id == kuitansi_id).first()
    if not k:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kuitansi tidak ditemukan")

    # Cross-tenant check (sama seperti approve)
    caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not caller_tenant:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant not found")

    if current_user["role"] == "KETUA_KEUANGAN":
        if k.tenant_id != caller_tenant.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kuitansi bukan dari jemaat Anda")
    elif current_user["role"] == "ADMIN_UNI":
        k_tenant = db.query(Tenant).filter(Tenant.id == k.tenant_id).first()
        if not k_tenant or k_tenant.nama_uni != caller_tenant.nama_uni:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Kuitansi bukan dari uni Anda")

    if k.status != "draft":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Kuitansi berstatus '{k.status}' tidak bisa di-reject (harus 'draft')",
        )

    # Reject
    k.status = "rejected"
    k.rejected_by_user_id = current_user["id"]
    k.rejected_at = utcnow()
    k.rejected_reason = payload.reason.strip()
    db.commit()
    db.refresh(k)

    # Audit log
    db.add(AuditLog(
        tenant_id=k.tenant_id,
        action=f"KUITANSI_REJECT_kuitansi_{k.id}_user_{current_user['id']}_reason='{k.rejected_reason[:50]}'",
        payload_hash=k.nomor_kuitansi,
    ))
    db.commit()

    # T24: Notify Bendahara (kuitansi creator) about rejection with reason
    if k.created_by_user_id and k.created_by_user_id != current_user["id"]:
        create_notification(
            db,
            user_id=k.created_by_user_id,
            tenant_id=k.tenant_id,
            event_type=EventType.KUITANSI_REJECTED,
            title="Kuitansi Anda ditolak",
            message=f"Kuitansi {k.nomor_kuitansi} ditolak. Alasan: {k.rejected_reason}",
            link="/bendahara",
            related_entity_type="kuitansi",
            related_entity_id=str(k.id),
            extra_data={
                "nomor_kuitansi": k.nomor_kuitansi,
                "rejected_reason": k.rejected_reason,
                "rejected_by_user_id": current_user["id"],
            },
            actor_user_id=current_user["id"],
            commit=False,
        )
        db.commit()

    return KuitansiApprovalOut(
        id=k.id,
        nomor_kuitansi=k.nomor_kuitansi,
        status=k.status,
        approved_by_user_id=k.approved_by_user_id,
        approved_at=k.approved_at.isoformat() if k.approved_at else None,
        rejected_by_user_id=k.rejected_by_user_id,
        rejected_at=k.rejected_at.isoformat() if k.rejected_at else None,
        rejected_reason=k.rejected_reason,
        created_by_user_id=k.created_by_user_id,
        total_pemberian_angka=k.total_pemberian_angka,
        tanggal_sabat=k.tanggal_sabat,
    )


@router.get("/kuitansi/pending", response_model=PendingListOut)
def list_pending_kuitansi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List kuitansi yang menunggu approval (status='draft').

    - KETUA_KEUANGAN: jemaat sendiri
    - ADMIN_UNI: semua jemaat di uni
    """
    if current_user["role"] not in ("KETUA_KEUANGAN", "ADMIN_UNI", "BENDAHARA"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role tidak eligible")

    # Scope tenant IDs
    if current_user["role"] == "BENDAHARA":
        # Bendahara: lihat draft miliknya sendiri (untuk koreksi)
        q = db.query(Kuitansi).filter(
            Kuitansi.tenant_id == current_user["tenant_id"],
            Kuitansi.status == "draft",
            Kuitansi.is_purged == False,
        ).order_by(Kuitansi.created_at.desc())
    elif current_user["role"] == "KETUA_KEUANGAN":
        q = db.query(Kuitansi).filter(
            Kuitansi.tenant_id == current_user["tenant_id"],
            Kuitansi.status == "draft",
            Kuitansi.is_purged == False,
        ).order_by(Kuitansi.created_at.desc())
    else:  # ADMIN_UNI
        from app.models.master import Uni, MisiKonferens
        caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
        if not caller_tenant or not caller_tenant.nama_uni:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Uni tidak terdefinisi")
        uni = db.query(Uni).filter(Uni.nama_resmi == caller_tenant.nama_uni).first()
        if not uni:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Uni not found")
        misi_ids = [m.id for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == uni.id).all()]
        tenant_ids = [t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id.in_(misi_ids)).all()]
        q = db.query(Kuitansi).filter(
            Kuitansi.tenant_id.in_(tenant_ids),
            Kuitansi.status == "draft",
            Kuitansi.is_purged == False,
        ).order_by(Kuitansi.created_at.desc())

    rows = q.all()

    items = []
    for k in rows:
        items.append(KuitansiApprovalOut(
            id=k.id,
            nomor_kuitansi=k.nomor_kuitansi,
            status=k.status,
            approved_by_user_id=k.approved_by_user_id,
            approved_at=k.approved_at.isoformat() if k.approved_at else None,
            rejected_by_user_id=k.rejected_by_user_id,
            rejected_at=k.rejected_at.isoformat() if k.rejected_at else None,
            rejected_reason=k.rejected_reason,
            created_by_user_id=k.created_by_user_id,
            total_pemberian_angka=k.total_pemberian_angka,
            tanggal_sabat=k.tanggal_sabat,
        ))

    return PendingListOut(items=items, total=len(items))


@router.get("/kuitansi/rejected")
def list_rejected_kuitansi(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List kuitansi yang di-reject (untuk Bendahara lihat & koreksi).

    - BENDAHARA: jemaat sendiri
    - KETUA_KEUANGAN: jemaat sendiri
    - ADMIN_UNI: semua jemaat di uni
    """
    if current_user["role"] not in ("KETUA_KEUANGAN", "ADMIN_UNI", "BENDAHARA"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role tidak eligible")

    if current_user["role"] in ("BENDAHARA", "KETUA_KEUANGAN"):
        q = db.query(Kuitansi).filter(
            Kuitansi.tenant_id == current_user["tenant_id"],
            Kuitansi.status == "rejected",
            Kuitansi.is_purged == False,
        ).order_by(Kuitansi.rejected_at.desc())
    else:
        from app.models.master import Uni, MisiKonferens
        caller_tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
        if not caller_tenant or not caller_tenant.nama_uni:
            return {"items": [], "total": 0}
        uni = db.query(Uni).filter(Uni.nama_resmi == caller_tenant.nama_uni).first()
        if not uni:
            return {"items": [], "total": 0}
        misi_ids = [m.id for m in db.query(MisiKonferens).filter(MisiKonferens.uni_id == uni.id).all()]
        tenant_ids = [t.id for t in db.query(Tenant).filter(Tenant.misi_konferens_id.in_(misi_ids)).all()]
        q = db.query(Kuitansi).filter(
            Kuitansi.tenant_id.in_(tenant_ids),
            Kuitansi.status == "rejected",
            Kuitansi.is_purged == False,
        ).order_by(Kuitansi.rejected_at.desc())

    rows = q.all()

    items = []
    for k in rows:
        items.append(KuitansiApprovalOut(
            id=k.id,
            nomor_kuitansi=k.nomor_kuitansi,
            status=k.status,
            approved_by_user_id=k.approved_by_user_id,
            approved_at=k.approved_at.isoformat() if k.approved_at else None,
            rejected_by_user_id=k.rejected_by_user_id,
            rejected_at=k.rejected_at.isoformat() if k.rejected_at else None,
            rejected_reason=k.rejected_reason,
            created_by_user_id=k.created_by_user_id,
            total_pemberian_angka=k.total_pemberian_angka,
            tanggal_sabat=k.tanggal_sabat,
        ))

    return {"items": items, "total": len(items)}
