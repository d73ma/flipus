"""
v2.0 M6 — OCR Pengeluaran (extract nota/kuitansi).

Pattern sama dengan M1 scanner.py tapi khusus nota pembayaran (bukan amplop persembahan).
- Upload foto nota/bukti transfer PLN, PDAM, Telkom, dll
- Ollama local extract: nominal + penerima + kategori_hint
- Simpan sebagai Pengeluaran dengan created_via='ocr', status='draft' (Bendahara review dulu)
- Bukti_path = path file upload
"""
import os
import uuid
import shutil
import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.models.pengeluaran import Pengeluaran
from app.models.kategori_pengeluaran import KategoriPengeluaran
from app.models.tenant import Tenant
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter()
UPLOAD_DIR = "storage/temp/pengeluaran"
os.makedirs(UPLOAD_DIR, exist_ok=True)

PROMPT_OCR_PENGELUARAN = """Kamu adalah OCR untuk nota/kuitansi pembayaran GMAHK UKIKT.
Ekstrak JSON valid (TANPA markdown):
{
  "jumlah": 0,
  "penerima": "...",
  "kategori_hint": "listrik|air|telpon|gaji_kostor|atk|transport|sewa|lainnya",
  "deskripsi": "...",
  "tanggal_nota": "YYYY-MM-DD atau kosong"
}
Aturan:
- jumlah dalam Rupiah (integer, tanpa Rp/titik/koma)
- penerima = nama vendor/supplier (contoh: PLN, PDAM, Telkom, Toko ATK)
- kategori_hint = kata kunci untuk klasifikasi
- Jika tidak terbaca, isi 0 dan set deskripsi = 'NEED_REVIEW'
- Jangan tambahkan teks di luar JSON.
"""


class OcrPengeluaranItem(BaseModel):
    path: str
    jumlah: int = 0
    penerima: str = ""
    kategori_hint: str = ""
    deskripsi: str = ""
    tanggal_nota: Optional[str] = None
    raw_ocr: Optional[str] = ""
    ocr_status: str = "NEED_REVIEW"


class OcrPengeluaranBatchOut(BaseModel):
    total_files: int
    items: List[OcrPengeluaranItem]


def _extract_with_ollama(image_path: str) -> dict:
    """Extract nota via Ollama (lokal). Kalau gagal return placeholder."""
    path = Path(image_path)
    if not path.exists():
        return {"error": "FILE_NOT_FOUND", "jumlah": 0, "penerima": "", "kategori_hint": "lainnya", "deskripsi": "NEED_REVIEW", "tanggal_nota": None}

    try:
        import ollama
    except ImportError:
        return {"jumlah": 0, "penerima": "", "kategori_hint": "lainnya", "deskripsi": "OLLAMA_LIB_MISSING", "tanggal_nota": None, "raw": ""}

    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        resp = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[{"role": "user", "content": PROMPT_OCR_PENGELUARAN, "images": [img_b64]}],
            options={"temperature": 0},
        )
        raw = resp["message"]["content"]
        # Parse JSON
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return {"jumlah": 0, "penerima": "", "kategori_hint": "lainnya", "deskripsi": "NEED_REVIEW", "tanggal_nota": None, "raw": raw}
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            data = {"jumlah": 0, "penerima": "", "kategori_hint": "lainnya", "deskripsi": "NEED_REVIEW", "tanggal_nota": None, "raw": raw}
        data["raw"] = raw
        return data
    except Exception as exc:
        logger.warning(f"[OCR-PENG] Ollama gagal: {exc}")
        return {"jumlah": 0, "penerima": "", "kategori_hint": "lainnya", "deskripsi": f"OLLAMA_ERROR: {type(exc).__name__}", "tanggal_nota": None, "raw": ""}


def _match_kategori(db: Session, tenant_id: int, hint: str) -> Optional[int]:
    """Coba match kategori dari hint. Return kategori_pengeluaran_id atau None."""
    if not hint:
        return None
    hint_low = hint.lower()
    alias_map = {
        "listrik": "LIS", "pln": "LIS",
        "air": "AIR", "pdam": "AIR",
        "telpon": "TLP", "telkom": "TLP",
        "gaji_kostor": "KOSTOR", "kostor": "KOSTOR", "gaji": "KOSTOR",
    }
    target_alias = alias_map.get(hint_low)
    if target_alias:
        k = db.query(KategoriPengeluaran).filter(
            KategoriPengeluaran.tenant_id == tenant_id,
            KategoriPengeluaran.alias == target_alias,
            KategoriPengeluaran.is_aktif == True,
        ).first()
        if k:
            return k.id
    return None


@router.post("/pengeluaran/ocr-batch-upload", response_model=OcrPengeluaranBatchOut)
async def ocr_batch_upload(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload 1+ foto nota. OCR extract nominal+penerima+kategori_hint."""
    if current_user["role"] != "BENDAHARA":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Bendahara yang boleh OCR upload.")

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        items = []
        saved_paths = []

        for f in files:
            safe_name = f"{uuid.uuid4().hex}_{f.filename}"
            full_path = os.path.join(UPLOAD_DIR, safe_name)
            with open(full_path, "wb") as out:
                shutil.copyfileobj(f.file, out)
            saved_paths.append(full_path)

            ocr_data = _extract_with_ollama(full_path)
            # jumlah bisa string error ("OLLAMA_ERROR:...") atau int — coerce aman
            try:
                jml = int(ocr_data.get("jumlah") or 0)
            except (ValueError, TypeError):
                jml = 0
            items.append(OcrPengeluaranItem(
                path=full_path,
                jumlah=jml,
                penerima=str(ocr_data.get("penerima") or ""),
                kategori_hint=str(ocr_data.get("kategori_hint") or ""),
                deskripsi=str(ocr_data.get("deskripsi") or ""),
                tanggal_nota=ocr_data.get("tanggal_nota"),
                raw_ocr=str(ocr_data.get("raw", ""))[:500],
                ocr_status="OK" if jml > 0 else "NEED_REVIEW",
            ))

        # Audit log (AuditLog schema has no detail/actor_user_id — pack info into action)
        db.add(AuditLog(
            tenant_id=current_user.get("tenant_id"),
            action=f"OCR_PENGELUARAN_BATCH_UPLOAD_count_{len(files)}_by_user_{current_user['id']}_saved_to_{UPLOAD_DIR[:32]}",
        ))
        db.commit()

        return OcrPengeluaranBatchOut(total_files=len(items), items=items)
    except HTTPException:
        raise
    except Exception as exc:
        import traceback as _tb
        print(f"[OCR-PENG-UPLOAD] FATAL: {type(exc).__name__}: {exc}\n{_tb.format_exc()}", flush=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"OCR batch-upload gagal: {type(exc).__name__}: {exc}")


class OcrPengeluaranSaveIn(BaseModel):
    """Single OCR result after Bendahara review/edit."""
    path: str
    jumlah: int
    penerima: str
    kategori_pengeluaran_id: int
    deskripsi: Optional[str] = ""
    metode_bayar: Optional[str] = "tunai"
    tanggal: Optional[str] = None  # default today


class OcrPengeluaranSaveOut(BaseModel):
    status: str
    saved_id: int
    nomor_pengeluaran: str
    kategori_nama: str
    is_rutin: bool


def _gen_nomor_pengeluaran_inline(db: Session, tenant_id: int, tanggal: str) -> str:
    """Inline nomor generator OUT-YYYYMMDD-NNN per tenant per hari. Fallback kalau utils file tidak ada."""
    today_compact = tanggal.replace("-", "")[:8]
    prefix = f"OUT-{today_compact}-"
    existing = db.query(Pengeluaran).filter(
        Pengeluaran.tenant_id == tenant_id,
        Pengeluaran.nomor_pengeluaran.like(f"{prefix}%"),
    ).all()
    seq = max([int(p.nomor_pengeluaran.split("-")[-1] or 0) for p in existing], default=0) + 1
    return f"{prefix}{seq:03d}"


@router.post("/pengeluaran/ocr-save", response_model=OcrPengeluaranSaveOut)
def ocr_save(
    body: OcrPengeluaranSaveIn,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save single OCR result as draft Pengeluaran. Bendahara wajib review sebelum submit."""
    if current_user["role"] != "BENDAHARA":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hanya Bendahara yang boleh save.")

    tenant_id = current_user["tenant_id"]
    kat = db.query(KategoriPengeluaran).filter(
        KategoriPengeluaran.id == body.kategori_pengeluaran_id,
        KategoriPengeluaran.tenant_id == tenant_id,
    ).first()
    if not kat:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategori tidak ditemukan untuk tenant ini.")

    tanggal = body.tanggal or datetime.now().strftime("%Y-%m-%d")
    id_rekap_mingguan = f"OCR-{tanggal}"
    nomor = _gen_nomor_pengeluaran_inline(db, tenant_id, tanggal)

    p = Pengeluaran(
        tenant_id=tenant_id,
        id_rekap_mingguan=id_rekap_mingguan,
        nomor_pengeluaran=nomor,
        tanggal=tanggal,
        tanggal_sabat=tanggal,  # simplified; can be enriched later
        kategori_pengeluaran_id=body.kategori_pengeluaran_id,
        jumlah=body.jumlah,
        deskripsi=body.deskripsi,
        penerima=body.penerima,
        metode_bayar=body.metode_bayar,
        bukti_path=body.path,
        status='draft',
        created_by_user_id=current_user["id"],
        created_via='ocr',
    )
    db.add(p)
    db.flush()
    db.add(AuditLog(
        tenant_id=tenant_id,
        action=f"OCR_PENGELUARAN_SAVE_id_{p.id}_by_user_{current_user['id']}_nomor_{nomor}_jumlah_{body.jumlah}_kategori_{kat.nama[:20]}",
    ))
    db.commit()

    return OcrPengeluaranSaveOut(
        status="draft",
        saved_id=p.id,
        nomor_pengeluaran=nomor,
        kategori_nama=kat.nama,
        is_rutin=kat.is_rutin,
    )