"""Kirim kuitansi digital ke WhatsApp umat (via Fonnte/Wablas)."""
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

def send_kuitansi_whatsapp(nomor_wa: str, pesan: str) -> dict:
    if not settings.WA_API_TOKEN or settings.WA_API_TOKEN.startswith("GANTI"):
        logger.warning("WA token belum diisi — simulasi kirim.")
        return {"status": "SIMULATED", "to": nomor_wa, "message": pesan}

    try:
        resp = httpx.post(
            settings.WA_API_URL,
            data={"target": nomor_wa, "message": pesan},
            headers={"Authorization": settings.WA_API_TOKEN},
            timeout=30,
        )
        return {"status": "SENT", "code": resp.status_code, "body": resp.text}
    except Exception as exc:
        logger.error("Gagal kirim WA: %s", exc)
        return {"status": "FAILED", "error": str(exc)}
