"""
Cloud Parsing — Gemini Vision untuk OCR + validasi logika.
Jika API key kosong, model invalid, atau response mencurigakan → return NEED_REVIEW.

v1.4 hardening (2026-08-22):
- Improved prompt: digit-by-digit emphasis untuk kurangi misread tulisan tangan
- NEED_REVIEW flag: response mencurigakan (nama kosong, nilai terlalu "bulat"/sering sama) flag manual review
- Debug log: image MD5 + raw Gemini response per call untuk verify cache vs real
- Confidence scoring: VALID_MATCH / NEED_REVIEW berdasarkan kelengkapan + plausibility
"""
import hashlib
import json
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# Model name dibaca dari settings.GEMINI_MODEL (env override).
# Default di config.py: gemini-1.5-flash (paling stabil sejak 2024).


def _img_hash(img_bytes: bytes) -> str:
    """MD5 hash untuk verifikasi image integrity (detect cache/hallucination)."""
    return hashlib.md5(img_bytes).hexdigest()[:12]


def _is_suspicious_response(parsed: dict) -> tuple[bool, str]:
    """
    Deteksi response yang kemungkinan hallucination/cache.
    Returns: (is_suspicious, reason)

    Heuristic konservatif (tidak over-flag untuk nilai legitimate):
    - Nama kosong/None → sangat suspect (OCR gagal total)
    - Total nol padahal parsed valid → OCR gagal baca angka
    - X == PT dan KEDUANYA persis nilai placeholder umum → placeholder
    """
    nama = (parsed.get("nama_umat") or "").strip()
    x = int(parsed.get("perpuluhan_X_angka") or 0)
    pt = int(parsed.get("PT_angka") or 0)

    # 1. Nama kosong → sangat suspect (OCR gagal baca)
    if not nama:
        return True, "NAMA_KOSONG"

    # 2. Total nol → OCR gagal baca angka
    if x + pt == 0:
        return True, "TOTAL_NOL"

    # 3. X == PT dan KEDUANYA nilai placeholder generic
    #    (misal: 1.000.000 persis sama untuk X & PT, sementara field khusus juga generic)
    placeholder_pairs = {(100000, 100000), (1000000, 1000000), (500000, 500000)}
    if (x, pt) in placeholder_pairs:
        return True, f"NILAI_PLACEHOLDER_X=PT={x}"

    return False, ""


def validate_with_gemini(kuitansi_payload: dict, image_path: str = None) -> dict:
    """
    Gemini vision OCR untuk amplop persembahan.

    Returns:
        dict dengan keys:
            - status: "VALID_MATCH" | "NEED_REVIEW"
            - ocr: {nama_umat, perpuluhan_X_angka, PT_angka, total_huruf}
            - sintaks_ok: bool
            - reason: str (kalau NEED_REVIEW)
            - img_hash: str (untuk debug cache detection)
    """
    # Skip kalau API key kosong atau masih placeholder (pre-inference reject,
    # TIDAK di-observe karena tidak ada inference yang terjadi).
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("GANTI"):
        logger.warning("Gemini API key belum di-set, skip OCR")
        return {
            "status": "NEED_REVIEW",
            "reason": "GEMINI_DISABLED",
            "sintaks_ok": None,
            "img_hash": None,
        }

    # FASE 5 Sprint 2 — Prometheus histogram `flipus_ai_inference_seconds`.
    # Wrap seluruh inference call supaya latency tercatat regardless of outcome
    # (ok / parse_fail / unreachable / suspicious).
    from app.core.metrics import observe_ai_inference

    model_name = getattr(settings, "GEMINI_MODEL", "unknown")
    with observe_ai_inference(provider="gemini", model=model_name) as obs:
        return _validate_with_gemini_impl(kuitansi_payload, image_path, model_name, obs)


def _validate_with_gemini_impl(
    kuitansi_payload: dict,
    image_path: str,
    model_name: str,
    obs,  # _OutcomeSetter dari observe_ai_inference
) -> dict:
    """Inner implementation of Gemini OCR — dipanggil di dalam observe_ai_inference."""
    # Compute image hash SEBELUM panggil Gemini (untuk verify cache)
    img_hash = None
    img_bytes = None
    if image_path and Path(image_path).exists():
        img_bytes = Path(image_path).read_bytes()
        img_hash = _img_hash(img_bytes)
        logger.info(f"[OCR] img_hash={img_hash} path={image_path} size={len(img_bytes)}")

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name)
        logger.info(f"[OCR] img_hash={img_hash} using model={model_name}")

        parts = []
        if img_bytes is not None:
            mime = "image/jpeg" if image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
            parts.append({"mime_type": mime, "data": img_bytes})
            # Prompt lebih eksplisit: digit-by-digit, anti-hallucination
            ocr_task = (
                "TUGAS: Baca foto amplop persembahan ini (tulisan tangan Indonesia).\n\n"
                "ATURAN KETAT:\n"
                "1. Baca SETIAP DIGIT angka satu per satu. Contoh: '5.697.000' → 5697000, BUKAN 5627200.\n"
                "2. JANGAN menebak atau mengarang angka. Kalau tidak terbaca, isi 0.\n"
                "3. JANGAN return nilai contoh/placeholder yang sama untuk semua gambar.\n"
                "4. Perpuluhan (X) = angka di baris pertama. PT (Persembahan Terpadu/Persembahan Terkait) = angka di baris kedua.\n"
                "5. Nama = teks di baris paling atas (biasanya setelah kata 'Nama' atau 'Nauner').\n\n"
                "OUTPUT JSON MURNI (TANPA markdown, TANPA komentar):\n"
                '{"nama_umat":"<string>","perpuluhan_X_angka":<int>,"PT_angka":<int>,"total_huruf":"<string>"}\n\n'
                "PENTING: Output HARUS JSON object valid. Jangan tambahkan teks di luar JSON."
            )
            parts.append(ocr_task)
        else:
            # Pure numeric validation (legacy fallback)
            parts.append(
                "Kamu auditor numerik GMAHK. Periksa JSON kuitansi ini:\n"
                f"{json.dumps(kuitansi_payload, default=str)}\n\n"
                "Validasi: total_pemberian_angka == perpuluhan_X_angka + PT_angka? "
                "Apakah angka konsisten dengan total_pemberian_huruf? "
                "Balas JSON: {\"status\":\"VALID_MATCH\"|\"NEED_REVIEW\",\"alasan\":\"...\"}"
            )

        resp = model.generate_content(parts)
        text = resp.text or ""
        logger.info(f"[OCR] img_hash={img_hash} raw_response={text[:500]}")

        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            logger.warning(f"[OCR] img_hash={img_hash} NO_JSON_IN_RESPONSE")
            obs.set_outcome("parse_fail")
            return {
                "status": "NEED_REVIEW",
                "reason": "GEMINI_PARSE_FAIL",
                "raw": text[:300],
                "img_hash": img_hash,
            }

        parsed = json.loads(text[start:end + 1])

        if "nama_umat" in parsed:
            # OCR result — validasi plausibility
            x = int(parsed.get("perpuluhan_X_angka") or 0)
            pt = int(parsed.get("PT_angka") or 0)

            # Deteksi hallucination/cache
            is_suspicious, reason = _is_suspicious_response(parsed)

            if x + pt > 0 and not is_suspicious:
                obs.set_outcome("ok")
                return {
                    "status": "VALID_MATCH",
                    "ocr": parsed,
                    "sintaks_ok": True,
                    "img_hash": img_hash,
                }

            # Suspect atau total nol → flag manual review
            logger.warning(f"[OCR] img_hash={img_hash} SUSPICIOUS reason={reason} ocr={parsed}")
            obs.set_outcome("suspicious")
            return {
                "status": "NEED_REVIEW",
                "ocr": parsed,
                "sintaks_ok": False,
                "reason": reason or "TOTAL_NOL",
                "img_hash": img_hash,
            }

        # Pure numeric validation result
        obs.set_outcome("ok")
        parsed["img_hash"] = img_hash
        return parsed

    except Exception as exc:
        logger.error(f"[OCR] img_hash={img_hash} EXCEPTION: {exc}")
        obs.set_outcome("error")
        return {
            "status": "NEED_REVIEW",
            "reason": "GEMINI_UNREACHABLE",
            "detail": str(exc),
            "img_hash": img_hash,
        }
