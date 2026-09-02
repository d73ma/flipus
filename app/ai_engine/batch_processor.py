"""
Batch processor — Gemini vision primary, Ollama fallback kalau Gemini suspect.

v1.4 hardening (2026-08-22):
- Pass img_hash per item untuk debug cache detection
- Pass status (VALID_MATCH / NEED_REVIEW) per item supaya Bendahara tahu mana yang perlu verify
- Fallback ke Ollama lokal kalau Gemini NEED_REVIEW (best-effort)
"""
import logging
from typing import List, Dict
from app.ai_engine.cloud_parser import validate_with_gemini
from app.ai_engine.local_ocr import extract_with_ollama, parse_ocr_payload
from app.services.financial_calculator import calculate_distribution

logger = logging.getLogger(__name__)


def _try_ollama_fallback(img_path: str, primary_ocr: dict) -> dict:
    """
    Kalau Gemini suspect (NEED_REVIEW), coba Ollama lokal sebagai cross-check.
    Best-effort: kalau Ollama juga gagal atau return kosong, keep primary result.
    """
    try:
        raw = extract_with_ollama(img_path)
        if raw.get("error"):
            logger.info(f"[OCR-FB] Ollama unavailable for {img_path}: {raw.get('error')}")
            return primary_ocr
        parsed_ollama = parse_ocr_payload(raw.get("raw", ""))
        if not parsed_ollama:
            logger.info(f"[OCR-FB] Ollama returned no JSON for {img_path}")
            return primary_ocr
        # Cross-check: kalau Ollama kasih nilai beda dari Gemini → pakai Ollama
        x_g = int(primary_ocr.get("perpuluhan_X_angka") or 0)
        pt_g = int(primary_ocr.get("PT_angka") or 0)
        x_o = int(parsed_ollama.get("perpuluhan_X_angka") or 0)
        pt_o = int(parsed_ollama.get("PT_angka") or 0)
        if (x_o != x_g or pt_o != pt_g) and (x_o + pt_o > 0):
            logger.info(f"[OCR-FB] img={img_path} Gemini={x_g}/{pt_g} Ollama={x_o}/{pt_o} → pakai Ollama")
            return {
                **primary_ocr,
                "nama_umat": parsed_ollama.get("nama_umat", primary_ocr.get("nama_umat", "")),
                "perpuluhan_X_angka": x_o,
                "PT_angka": pt_o,
                "total_huruf": parsed_ollama.get("total_huruf", ""),
                "ocr_source": "ollama_fallback",
                "ocr_status": "VALID_MATCH",
            }
        return primary_ocr
    except Exception as exc:
        logger.warning(f"[OCR-FB] Exception: {exc}")
        return primary_ocr


def process_batch(image_paths: List[str]) -> Dict:
    results = []
    total_x = 0
    total_pt = 0
    need_review_count = 0

    for idx, img_path in enumerate(image_paths, start=1):
        gemini = validate_with_gemini({}, img_path)
        ocr = gemini.get("ocr", {}) if isinstance(gemini, dict) else {}
        img_hash = gemini.get("img_hash") if isinstance(gemini, dict) else None
        ocr_status = gemini.get("status", "NEED_REVIEW") if isinstance(gemini, dict) else "NEED_REVIEW"

        x_val = int(ocr.get("perpuluhan_X_angka") or 0)
        pt_val = int(ocr.get("PT_angka") or 0)
        nama = ocr.get("nama_umat", "") or ""
        huruf = ocr.get("total_huruf", "") or ""

        # Kalau Gemini suspect (NEED_REVIEW), coba Ollama fallback
        ocr_source = "gemini"
        if ocr_status == "NEED_REVIEW":
            ocr = _try_ollama_fallback(img_path, ocr)
            ocr_source = ocr.get("ocr_source", "gemini")
            ocr_status = ocr.get("ocr_status", ocr_status)
            x_val = int(ocr.get("perpuluhan_X_angka") or 0)
            pt_val = int(ocr.get("PT_angka") or 0)
            nama = ocr.get("nama_umat", "") or nama
            huruf = ocr.get("total_huruf", "") or huruf

        total_x += x_val
        total_pt += pt_val

        dist = calculate_distribution(x_val, pt_val)

        # Tandai NEED_REVIEW untuk frontend
        needs_manual_review = ocr_status != "VALID_MATCH"
        if needs_manual_review:
            need_review_count += 1

        results.append({
            "index": idx,
            "path": img_path,
            "nama_umat": nama,
            "perpuluhan_X_angka": x_val,
            "PT_angka": pt_val,
            "total_pemberian_angka": x_val + pt_val,
            "porsi_kantor_misi": dist["porsi_kantor_misi"],
            "porsi_kas_jemaat": dist["porsi_kas_jemaat"],
            "raw_total_huruf": huruf,
            "cloud_validation": gemini,
            "img_hash": img_hash,
            "ocr_status": ocr_status,            # VALID_MATCH | NEED_REVIEW
            "ocr_source": ocr_source,            # gemini | ollama_fallback
            "needs_manual_review": needs_manual_review,
        })

    return {
        "total_amplop": len(image_paths),
        "total_x_terbaca": total_x,
        "total_pt_terbaca": total_pt,
        "need_review_count": need_review_count,
        "items": results,
    }