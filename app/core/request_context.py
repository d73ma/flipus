"""
FASE 3 Sprint 3 (S1) — Request context middleware.

Menghubungkan setiap HTTP request ke contextvars yang dipakai JSONFormatter:
  - request_id  → UUID 16-char (header X-Request-ID jika ada, else generated)
  - tenant_id   → resolved dari JWT (jika route pakai Depends(get_current_user))
  - user_id     → dari JWT 'sub' claim
  - XFF client_ip  → di-resolve sekali di sini untuk reuse di audit logs

Middleware ini berjalan SETIAP request, sehingga semua log line yang
dikeluarkan selama request processing otomatis punya context fields yang
sama — penting untuk forensic (grep `tenant_id=5 user_id=12 request_id=...`
di log aggregator).
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logger import (
    request_id_var,
    tenant_id_var,
    user_id_var,
    set_request_context,
)

_logger = logging.getLogger("app.core.request_context")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach request-scoped context (request_id, ip) ke contextvars.

    Tenant + user ID baru ter-resolve setelah JWT dependency jalan (di
    dalam handler). Untuk itu middleware ini menyediakan helper
    `request.state.request_id` dan `request.state.client_ip` yang bisa
    dipakai handler untuk update contextvars via set_request_context().
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        # 1. Resolve request_id — dari header X-Request-ID (kalau ada),
        #    else generate baru. Mengikuti konvensi 12-char prefix (cukup
        #    untuk correlation, tidak bocor UUID internals).
        incoming_rid = request.headers.get("x-request-id", "").strip()
        request_id = incoming_rid if incoming_rid else None

        # 2. Resolve client IP — XFF first, fallback ke socket address.
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            client_ip = xff.split(",")[0].strip()
        else:
            client_ip = (request.client.host if request.client else "unknown")

        # 3. Set contextvars — request_id + IP. tenant_id/user_id akan
        #    di-set oleh handler setelah auth dependency resolved.
        set_request_context(request_id=request_id, tenant_id=None, user_id=None)
        request.state.request_id = request_id_var.get()
        request.state.client_ip = client_ip

        # 4. Log masuk/keluar request (ringan, level INFO). Menghindari
        #    flood untuk /docs, /openapi.json, dll.
        skip_paths = ("/docs", "/openapi.json", "/redoc", "/favicon.ico")
        should_log = not any(request.url.path.startswith(p) for p in skip_paths)

        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            # Update user/tenant jika handler sempat set di state
            if hasattr(request.state, "tenant_id"):
                tenant_id_var.set(str(request.state.tenant_id))
            if hasattr(request.state, "user_id"):
                user_id_var.set(str(request.state.user_id))

            if should_log:
                _logger.info(
                    "request_completed method=%s path=%s status=%d elapsed_ms=%.1f ip=%s",
                    request.method,
                    request.url.path,
                    response.status_code,
                    elapsed_ms,
                    client_ip,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "http_status": response.status_code,
                        "elapsed_ms": round(elapsed_ms, 1),
                        "client_ip": client_ip,
                    },
                )
            # Echo request_id back supaya klien bisa correlation
            response.headers["X-Request-ID"] = request_id_var.get()
            return response
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if should_log:
                _logger.exception(
                    "request_failed method=%s path=%s elapsed_ms=%.1f ip=%s exc=%s",
                    request.method,
                    request.url.path,
                    elapsed_ms,
                    client_ip,
                    type(exc).__name__,
                    extra={
                        "http_method": request.method,
                        "http_path": request.url.path,
                        "elapsed_ms": round(elapsed_ms, 1),
                        "client_ip": client_ip,
                        "exc_type": type(exc).__name__,
                    },
                )
            raise
        finally:
            # Reset contextvars supaya next request tidak inherit
            # (defensive — contextvars sebenarnya auto-reset per task,
            # tapi explicit reset aman untuk threadpool workers)
            tenant_id_var.set("-")
            user_id_var.set("-")
            request_id_var.set("-")