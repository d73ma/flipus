"""
Local Vision Engine — Ollama + Qwen2.5-VL (Offline).
Fallback: jika Ollama tidak tersedia, kembalikan placeholder agar
alur batch tidak crash (bendahara tinggal input manual).
"""
import base64
import json
import logging
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

PROMPT_OCR = """Kamu adalah OCR untuk amplop persembahan GMAHK UKIKT.
Ekstrak JSON valid (TANPA markdown):
{
  "nama_umat": "...",
  "perpuluhan_X_angka": 0,
  "PT_angka": 0,
  "total_huruf": "..."
}
Aturan:
- Angka dalam Rupiah (integer, tanpa Rp/titik).
- Jika tulisan tidak terbaca, isi 0 dan flag 'NEED_REVIEW'.
- Jangan tambahkan teks di luar JSON.
"""

def extract_with_ollama(image_path: str) -> dict:
    path = Path(image_path)
    if not path.exists():
        return {"error": "FILE_NOT_FOUND", "path": image_path}

    try:
        import ollama
    except ImportError:
        return {"error": "OLLAMA_LIB_MISSING", "fallback": True}

    try:
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        response = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": PROMPT_OCR,
                    "images": [img_b64],
                }
            ],
            options={"temperature": 0},
        )
        raw = response["message"]["content"]
        return {"raw": raw, "source": "ollama_local"}
    except Exception as exc:
        logger.warning("Ollama gagal: %s — fallback manual.", exc)
        return {"error": "OLLAMA_UNREACHABLE", "fallback": True, "detail": str(exc)}

def parse_ocr_payload(raw_text: str) -> dict:
    """Ambil JSON object dari teks yang mungkin ada penjelasan di luarnya."""
    if not raw_text:
        return {}
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(raw_text[start:end + 1])
    except json.JSONDecodeError:
        return {}
