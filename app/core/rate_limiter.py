"""
FASE 3 Sprint 1 - Rate Limiter setup (K1, K2)

Menggunakan slowapi dengan in-memory storage (cukup untuk single-worker SQLite).

CATATAN PRODUKSI:
- Untuk deployment multi-worker (gunicorn -w N atau uvicorn --workers N),
  ganti `storage_uri` ke Redis URL, contoh:
      storage_uri="redis://redis:6379/0"
  Pakai environment variable: REDIS_URL atau RATE_LIMIT_STORAGE_URI.
- Dependency `limits[redis]==3.13.0` sudah ada di requirements.txt untuk ini.
- Di-development (single-worker SQLite), in-memory storage aman dan zero-config.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func_by_ip(request: Request) -> str:
    """Default key: remote IP address (X-Forwarded-For handled oleh slowapi)."""
    return get_remote_address(request)


def _key_func_by_phone(request: Request) -> str:
    """
    Key khusus untuk endpoint WhatsApp webhook.
    Menggunakan field `From` dari body Twilio (form-encoded), fallback ke IP.
    Dipakai untuk K2 (anti-spam dari nomor pengirim yang sama).
    """
    try:
        # Twilio mengirim 'From' di form body; kita baca via request.form() di handler,
        # tapi untuk key_func kita pakai cache dari state jika tersedia.
        phone = getattr(request.state, "wa_from", None)
        if phone:
            return f"wa:{phone}"
    except Exception:
        pass
    return f"ip:{get_remote_address(request)}"


# Limiter global - diaplikasikan via SlowAPIMiddleware di main.py
# Storage: memory:// (single-worker). Untuk multi-worker pakai Redis.
#
# headers_enabled=False: endpoint FLIPUS mengembalikan Pydantic model
# (TokenOut, UserOut, dll), bukan starlette.responses.Response. Jika True,
# slowapi mencoba inject X-RateLimit-* headers ke response object yang
# tidak ada → RuntimeError "parameter 'response' must be an instance of
# starlette.responses.Response". Trade-off: klien tidak dapat header
# X-RateLimit-*, tapi rate-limit tetap enforced (429 saat exceeded).
limiter = Limiter(
    key_func=_key_func_by_ip,
    storage_uri="memory://",
    default_limits=[],  # Tidak ada default — opt-in per endpoint
    headers_enabled=False,
    strategy="fixed-window",  # Window-based counter (simple & cukup untuk K1/K2)
)


__all__ = ["limiter", "_key_func_by_phone"]
