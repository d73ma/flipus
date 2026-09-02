import os
import uuid
import shutil
import random
import time
from datetime import datetime
from app.core.security import utcnow
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_engine.batch_processor import process_batch
from app.core.database import get_db
from app.core.security import encrypt_pii
from app.api.v1.auth import get_current_user
from app.models.transaction import Kuitansi
from app.models.tenant import Tenant
from app.models.audit import AuditLog
from app.models.master import PersentaseConfig
from app.utils.nomor_kuitansi import generate_nomor_kuitansi
from app.utils.number_to_words import terbilang
from app.utils.sabat_counter import get_current_sabat, get_effective_sabat_for_input

router = APIRouter()
UPLOAD_DIR = "storage/temp"


class BatchItemOut(BaseModel):
    index: int
    path: str
    nama_umat: str
    perpuluhan_X_angka: int
    PT_angka: int
    total_pemberian_angka: int
    porsi_kantor_misi: int
    porsi_kas_jemaat: int
    raw_total_huruf: Optional[str] = ""
    img_hash: Optional[str] = None
    ocr_status: Optional[str] = "NEED_REVIEW"
    ocr_source: Optional[str] = "gemini"
    needs_manual_review: Optional[bool] = True


class BatchResultOut(BaseModel):
    total_amplop: int
    total_x_terbaca: int
    total_pt_terbaca: int
    need_review_count: Optional[int] = 0
    items: List[BatchItemOut]


@router.post("/batch-upload", response_model=BatchResultOut)
async def batch_upload(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user["role"] not in ("BENDAHARA", "KETUA_KEUANGAN", "PENDETA"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role tidak diizinkan")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    paths = []
    for f in files:
        safe_name = f"{uuid.uuid4().hex}_{f.filename}"
        full_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(full_path, "wb") as out:
            shutil.copyfileobj(f.file, out)
        paths.append(full_path)

    result = process_batch(paths)
    return BatchResultOut(**result)


# ===== OCR Save Batch =====

class OcrItemIn(BaseModel):
    """Item dari OCR review (sudah diedit Bendahara kalau perlu)."""
    path: Optional[str] = None
    nama_umat: Optional[str] = None
    nomor_whatsapp: Optional[str] = None
    perpuluhan_x_angka: int = 0
    pt_angka: int = 0
    khusus_angka: int = 0


class OcrBatchSaveIn(BaseModel):
    items: List[OcrItemIn]
    tanggal_sabat: Optional[str] = None
    id_rekap_mingguan: Optional[str] = None
    send_auto_thanks: bool = True


class OcrSavedItem(BaseModel):
    nomor_kuitansi: str
    nama_umat: Optional[str] = None
    perpuluhan_x_angka: int
    pt_angka: int
    khusus_angka: int
    total_pemberian_angka: int
    auto_thanks_sent: bool = False


class OcrBatchSaveOut(BaseModel):
    status: str
    saved_count: int
    auto_thanks_count: int
    items: List[OcrSavedItem]


def _get_persentase(db: Session, tenant: Tenant) -> dict:
    if tenant.misi_konferens_id is None:
        return {"pct_x_jemaat": 1.0, "pct_pt_jemaat": 0.5, "pct_khusus_jemaat": 0.0}
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


@router.post("/save-batch", response_model=OcrBatchSaveOut)
def save_ocr_batch(
    payload: OcrBatchSaveIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Save hasil OCR review (setelah diedit Bendahara) sebagai kuitansi.

    Flow:
    1. Bendahara upload foto amplop → batch_upload (OCR)
    2. Frontend tampilkan OcrReview dengan item-item hasil OCR
    3. Bendahara review/edit nama & nominal
    4. Submit → endpoint ini save semua item sebagai Kuitansi
    5. Auto-thanks WA per item kalau ada nomor_whatsapp

    RBAC: BENDAHARA/KETUA_KEUANGAN
    """
    if current_user["role"] not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya bendahara/ketua keuangan")

    tenant = db.query(Tenant).filter(Tenant.id == current_user["tenant_id"]).first()
    if not tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    # RBAC safeguard (T67): tenant_id HARUS dari current_user, BUKAN dari payload.
    # user tidak bisa supply tenant_id lain lewat Pydantic model — tapi log here
    # supaya ada audit trail kalau ada perubahan di masa depan.
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"[OCR save-batch] user_id={current_user['id']} role={current_user['role']} "
        f"tenant_id={tenant.id} tenant_slug={tenant.slug} items_count={len(payload.items)}"
    )

    # Determine tanggal_sabat (T111: pakai sabat terakhir yang sudah lewat, bukan UTC today)
    if payload.tanggal_sabat:
        tanggal_sabat = payload.tanggal_sabat
    else:
        sabat_info = get_effective_sabat_for_input()
        tanggal_sabat = sabat_info["tanggal_sabat"]

    # Determine id_rekap
    id_rekap = payload.id_rekap_mingguan
    if not id_rekap:
        today = utcnow().strftime("%Y%m%d")
        id_rekap = f"RK-{today}"

    # Get persentase config
    pct = _get_persentase(db, tenant)

    saved_items = []
    auto_thanks_count = 0

    # Existing nomor urut.
    #
    # FIX 2026-08-23:
    # Nomor kuitansi format `001/NT/VIII/26` di-namespace per BULAN, bukan per tanggal.
    # Counter reset tiap bulan Romawi. Query sebelumnya filter `tanggal_sabat='2026-08-22'`
    # sehingga row dari 2026-08-01 dan 2026-08-15 (max=017/NT/VIII/26) ter-exclude →
    # base_count stale → urutan reset ke 1 → UNIQUE constraint failed.
    #
    # Fix: lookup semua nomor di bulan yang sama (year-month dari tanggal_sabat),
    # ignore is_purged, parse max urutan dari prefix "001/" → 1, dst.
    try:
        target_year_month = tanggal_sabat[:7]  # "2026-08-22" → "2026-08"
    except (TypeError, IndexError):
        target_year_month = ""

    if target_year_month:
        existing_numbers_raw = (
            db.query(Kuitansi.nomor_kuitansi)
            .filter(Kuitansi.tenant_id == tenant.id)
            .filter(Kuitansi.tanggal_sabat.like(f"{target_year_month}%"))
            .all()
        )
    else:
        existing_numbers_raw = (
            db.query(Kuitansi.nomor_kuitansi)
            .filter(Kuitansi.tenant_id == tenant.id)
            .all()
        )

    max_urutan = 0
    for (nomor,) in existing_numbers_raw:
        try:
            urutan_str = (nomor or "").split("/")[0]
            n = int(urutan_str)
            if n > max_urutan:
                max_urutan = n
        except (ValueError, IndexError, AttributeError):
            continue
    base_count = max_urutan

    from app.services.whatsapp import send_auto_thanks

    for i, item in enumerate(payload.items):
        urutan = base_count + i + 1
        # Safety net: kalau ternyata nomor masih konflik (legacy data, format beda, dll),
        # increment sampai ketemu nomor yang belum dipakai.
        while True:
            try:
                nomor_candidate = generate_nomor_kuitansi(
                    urutan=urutan,
                    initial_jemaat=tenant.initial_jemaat or "XX",
                    tanggal=datetime.fromisoformat(tanggal_sabat),
                )
            except Exception:
                nomor_candidate = f"KPT-{utcnow().strftime('%Y%m%d%H%M%S')}-{urutan}"

            existing = (
                db.query(Kuitansi)
                .filter(Kuitansi.nomor_kuitansi == nomor_candidate)
                .first()
            )
            if not existing:
                nomor = nomor_candidate
                break
            urutan += 1
        base_count = urutan  # update untuk item berikutnya di batch yang sama

        total_x = item.perpuluhan_x_angka
        total_pt = item.pt_angka
        total_khusus = item.khusus_angka
        total_all = total_x + total_pt + total_khusus

        # T81 (revisi 2026-08-23): Jerry Model B (hierarchical) — porsi_uni
        # adalah fraction of (1 - pct_jemaat), bukan of total. Constrain
        # pct_jemaat + pct_uni ≤ 1.0 sudah TIDAK berlaku.
        from app.utils.porsi_calculator import compute_porsi
        p = compute_porsi(
            x=total_x, pt=total_pt, kh=total_khusus,
            pct_x_jemaat=pct["pct_x_jemaat"],
            pct_pt_jemaat=pct["pct_pt_jemaat"],
            pct_khusus_jemaat=pct["pct_khusus_jemaat"],
            pct_x_uni=pct.get("pct_x_uni", 0.0),
            pct_pt_uni=pct.get("pct_pt_uni", 0.0),
            pct_khusus_uni=pct.get("pct_khusus_uni", 0.0),
        )
        pj_x, pj_pt, pj_kh = p["pj_x"], p["pj_pt"], p["pj_kh"]
        pu_x, pu_pt, pu_kh = p["pu_x"], p["pu_pt"], p["pu_kh"]
        pm_x, pm_pt, pm_kh = p["pm_x"], p["pm_pt"], p["pm_kh"]

        try:
            nama_enc = encrypt_pii(item.nama_umat) if item.nama_umat else None
        except Exception as e:
            import sys as _sys, traceback as _tb
            print(f"[OCR] encrypt_pii(nama) failed: {e}\n{_tb.format_exc()}", file=_sys.stderr)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Gagal mengenkripsi nama umat. Hubungi admin (cek log server untuk detail).",
            )
        try:
            wa_enc = encrypt_pii(item.nomor_whatsapp) if item.nomor_whatsapp else None
        except Exception as e:
            import sys as _sys, traceback as _tb
            print(f"[OCR] encrypt_pii(wa) failed: {e}\n{_tb.format_exc()}", file=_sys.stderr)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Gagal mengenkripsi nomor WhatsApp. Hubungi admin (cek log server untuk detail).",
            )

        k = Kuitansi(
            tenant_id=tenant.id,
            id_rekap_mingguan=id_rekap,
            nomor_kuitansi=nomor,
            tanggal_sabat=tanggal_sabat,
            nama_umat_encrypted=nama_enc,
            nomor_whatsapp_encrypted=wa_enc,
            foto_amplop_path=item.path,
            perpuluhan_x_angka=total_x,
            pt_angka=total_pt,
            khusus_angka=total_khusus,
            total_pemberian_angka=total_all,
            total_pemberian_huruf=terbilang(total_all),
            porsi_kantor_misi=pm_x + pm_pt,
            porsi_kas_jemaat=(pj_pt + pj_x) + (pj_kh),
            porsi_khusus_misi=pm_kh,
            porsi_khusus_jemaat=pj_kh + pu_kh,  # KH share jemaat + uni (Model A)
        )
        # T5 (FASE 3 Sprint 1): race-condition guard dengan SAVEPOINT per item.
        # Loop inner sebelumnya hanya cek "stale read" (existing.first()),
        # tapi tidak catch IntegrityError dari UNIQUE constraint pada
        # nomor_kuitansi saat insert. Antara existing.first() dan db.flush()
        # request paralel bisa menyisipkan nomor yang sama. Solusi: SAVEPOINT
        # per item — kalau IntegrityError, rollback HANYA savepoint (item ini),
        # bukan seluruh transaksi batch. Item lain yang sudah insert tetap aman.
        # Bounded retry (5x) + jitter 10-50ms untuk kurangi thundering herd.
        _insert_attempts = 0
        _sp = db.begin_nested()  # SAVEPOINT per item
        try:
            while True:
                try:
                    db.add(k)
                    db.flush()
                    _sp.commit()  # release savepoint
                    break  # sukses insert, lanjut item berikutnya
                except IntegrityError as _ie:
                    # Rollback HANYA savepoint (item ini), bukan transaksi utama.
                    _sp.rollback()
                    _insert_attempts += 1
                    if _insert_attempts > 5:
                        import sys as _sys, traceback as _tb
                        print(f"[OCR] IntegrityError retry exhausted (5x) for item idx={i}: {_ie}\n{_tb.format_exc()}", file=_sys.stderr)
                        raise HTTPException(
                            status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Server sibuk memproses kuitansi paralel. Silakan coba ulang dalam beberapa detik.",
                        )
                    # Increment urutan + jitter (10-50ms) untuk kurangi contention.
                    urutan += 1
                    base_count = urutan  # update untuk item berikutnya
                    # Re-generate nomor dengan urutan baru.
                    try:
                        nomor = generate_nomor_kuitansi(
                            urutan=urutan,
                            initial_jemaat=tenant.initial_jemaat or "XX",
                            tanggal=datetime.fromisoformat(tanggal_sabat),
                        )
                    except Exception:
                        nomor = f"KPT-{utcnow().strftime('%Y%m%d%H%M%S')}-{urutan}"
                    k.nomor_kuitansi = nomor
                    k.id = None  # reset supaya tidak konflik PK setelah rollback
                    _sp = db.begin_nested()  # buka savepoint baru
                    time.sleep(0.01 + random.random() * 0.04)
                    continue
        except Exception as e:
            try:
                _sp.rollback()
            except Exception:
                pass
            import sys as _sys, traceback as _tb
            print(f"[OCR] db insert failed: {e}\n{_tb.format_exc()}", file=_sys.stderr)
            db.rollback()
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Gagal menyimpan kuitansi ke database. Data input sudah aman di form, silakan coba ulang atau hubungi admin.",
            )

        auto_thanks_sent = False
        if payload.send_auto_thanks and item.nomor_whatsapp:
            try:
                resp = send_auto_thanks(
                    phone=item.nomor_whatsapp,
                    nama=item.nama_umat or "Saudara",
                    nama_jemaat=tenant.nama_jemaat_lokal,
                    tanggal_sabat=tanggal_sabat,
                    perpuluhan_x=total_x,
                    pt=total_pt,
                    khusus=total_khusus,
                    nama_pendeta=tenant.nama_pendeta or "Pendeta",
                    nama_bendahara=tenant.nama_bendahara or "Bendahara",
                )
                auto_thanks_sent = isinstance(resp, dict) and resp.get("status") == "sent"
                if auto_thanks_sent:
                    auto_thanks_count += 1
            except Exception:
                pass

        saved_items.append(OcrSavedItem(
            nomor_kuitansi=nomor,
            nama_umat=item.nama_umat,
            perpuluhan_x_angka=total_x,
            pt_angka=total_pt,
            khusus_angka=total_khusus,
            total_pemberian_angka=total_all,
            auto_thanks_sent=auto_thanks_sent,
        ))

    # Audit log
    db.add(AuditLog(
        tenant_id=tenant.id,
        action=f"OCR_BATCH_SAVE_user_{current_user['id']}_count_{len(saved_items)}",
        payload_hash=id_rekap,
        porsi_dana_misi=sum(i.perpuluhan_x_angka + i.pt_angka for i in payload.items),
    ))
    db.commit()

    return OcrBatchSaveOut(
        status="ok",
        saved_count=len(saved_items),
        auto_thanks_count=auto_thanks_count,
        items=saved_items,
    )
