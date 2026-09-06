"""
FASE 3 Sprint 3 (S1) — Centralized Structured JSON Logging.

Fungsi:
  - setup_logging(level): configure root logger dengan JSONFormatter.
  - get_logger(name): child logger (idempotent, standar stdlib).
  - RequestContextMiddleware: attach request_id, tenant_id, user_id ke
    contextvars supaya setiap log line otomatis punya field ts/level/logger/
    msg + context. Cocok untuk audit trail + grep di production.

Kenapa JSON?
  - Grep-able di log aggregator (Loki, Elasticsearch, Cloud Logging).
  - Field terstruktur: tenant_id, user_id, request_id, level, ts, logger,
    msg, exception. Tidak perlu regex parsing untuk human fields.
  - Memudahkan correlation antar-service (request_id propagates ke semua
    child logger calls).

Kenapa contextvars (bukan Flask g / threading.local)?
  - FastAPI jalan di async (asyncio) — contextvars adalah standard library
    untuk menyimpan data per-task secara aman tanpa leakage antar-request.
  - Tidak affected by gunicorn workers (each worker punya contextvars sendiri).

TIDAK menambah dependency baru — hanya stdlib `logging` + `json`.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os

# ---------------------------------------------------------------------------
# FASE 5 Sprint 1 — Static service identity.
# ---------------------------------------------------------------------------
# Constants di-include di setiap log line agar multi-service aggregator
# (Loki / CloudWatch / Datadog) bisa filter `{service="flipus"}` tanpa parse
# nama logger (yang bisa bervariasi jika module di-rename).
# Override via env `FLIPUS_SERVICE_NAME` / `FLIPUS_SERVICE_VERSION` bila
# perlu jalankan multiple build (canary / blue-green) tanpa混淆 log.
import os as _os_identity
import sys
import time
import uuid
from typing import Any

SERVICE_NAME: str = _os_identity.environ.get("FLIPUS_SERVICE_NAME", "flipus")
SERVICE_VERSION: str = _os_identity.environ.get("FLIPUS_SERVICE_VERSION", "1.5.0")


# ---------------------------------------------------------------------------
# Context variables — attached per request via middleware
# ---------------------------------------------------------------------------

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
tenant_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tenant_id", default="-"
)
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default="-"
)


def set_request_context(
    request_id: str | None = None,
    tenant_id: Any | None = None,
    user_id: Any | None = None,
) -> str:
    """Set request-scoped context. Returns request_id (new or existing)."""
    if request_id is None:
        request_id = request_id_var.get()
        if request_id == "-":
            request_id = uuid.uuid4().hex[:16]
    request_id_var.set(request_id)
    if tenant_id is not None:
        tenant_id_var.set(str(tenant_id))
    if user_id is not None:
        user_id_var.set(str(user_id))
    return request_id


def get_request_context() -> dict[str, str]:
    """Snapshot context saat ini untuk di-attach ke log records."""
    return {
        "request_id": request_id_var.get(),
        "tenant_id": tenant_id_var.get(),
        "user_id": user_id_var.get(),
    }


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------

_RESERVED_LOGRECORD_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JSONFormatter(logging.Formatter):
    """Format LogRecord sebagai single-line JSON.

    Output schema:
      {
        "ts": "2026-09-02T15:00:00.123Z",   # ISO 8601 UTC
        "level": "INFO",                     # INFO/DEBUG/WARNING/ERROR/CRITICAL
        "logger": "app.api.v1.scanner",      # logger name
        "msg": "OCR finished in 2.3s",       # formatted message
        "request_id": "abc123...",           # contextvar
        "tenant_id": "5",                    # contextvar (or "-")
        "user_id": "12",                     # contextvar (or "-")
        # ... extra fields (anything passed as `extra={"key": "val"}`)
      }

    Exception info (jika logger.exception() dipanggil) ditambahkan sebagai
    field `exc` dengan formatted traceback (bukan repr object).
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base fields
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
        ts += ".{:03d}Z".format(int(record.msecs))

        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            # FASE 5 Sprint 1 — Static service identity (untuk multi-service
            # log aggregator filtering, misal Loki {service="flipus"}).
            "service": SERVICE_NAME,
            "service_version": SERVICE_VERSION,
        }

        # Contextvars (request-scoped)
        ctx = get_request_context()
        payload.update(ctx)

        # Extra fields dari logger.xxx(..., extra={"foo": "bar"})
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_ATTRS:
                continue
            if key.startswith("_"):
                continue
            if key in payload:
                continue
            # Jangan masukkan objek yang tidak JSON-serializable secara default
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        # Exception traceback
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.exc_text:
            payload["exc"] = record.exc_text
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            # Fallback — should never happen, but log safely
            return json.dumps(
                {
                    "ts": ts,
                    "level": "ERROR",
                    "logger": "app.core.logger",
                    "msg": "JSONFormatter failed: {} | original={}".format(
                        exc, record.getMessage()
                    ),
                }
            )


# ---------------------------------------------------------------------------
# setup_logging()
# ---------------------------------------------------------------------------

_configured = False


def setup_logging(
    level: str | None = None,
    stream: Any = None,
    force: bool = False,
) -> logging.Logger:
    """Configure root logger untuk JSON output.

    Args:
        level: log level string (DEBUG/INFO/WARNING/ERROR). Default dari
            env LOG_LEVEL atau INFO.
        stream: output stream (default sys.stdout).
        force: kalau True, reset existing handlers (berguna untuk tests).

    Returns:
        root logger (idempotent — multiple calls aman, hanya init sekali
        kecuali force=True).
    """
    global _configured
    if _configured and not force:
        return logging.getLogger()

    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if stream is None:
        stream = sys.stdout

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    if force:
        for h in list(root.handlers):
            root.removeHandler(h)

    # Avoid duplicate handler kalau module di-reimport
    has_json_handler = any(
        getattr(h, "_flipus_json", False) for h in root.handlers
    )
    if not has_json_handler:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        handler._flipus_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    # Matikan noisy third-party loggers (kecuali DEBUG requested)
    if level != "DEBUG":
        for noisy in ("urllib3", "httpx", "httpcore", "sqlalchemy.engine"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper untuk `logging.getLogger(name)`.

    Bisa dipanggil sebelum setup_logging() — formatter akan tetap dipakai
    begitu setup_logging() dipanggil di startup.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# FASE 5 Sprint 1 — Security event logger (consumed by FASE 5 Sprint 2 metrics).
# ---------------------------------------------------------------------------
# Counter `security_events_total{event_type}` akan di-instrument di S5-2 via
# prometheus_client. Untuk saat ini hanya emits structured log line dengan
# field `event_type` aggregator-friendly — siap untuk di-tap di Grafana /
# CloudWatch alarm: kalau event_type="tenant_scope_violation" >10/menit →
# possible probing attack.

def log_security_event(
    event_type: str,
    *,
    request: Any = None,
    user_id: Any = None,
    tenant_id: Any = None,
    detail: str = "",
) -> None:
    """Emit security event log line.

    Args:
        event_type: salah satu konstanta di bawah (string label).
        request: optional FastAPI Request untuk fallback IP.
        user_id: attacker / caller user id (kalau ada, "-").
        tenant_id: caller tenant (atau victim tenant, tergantung event).
        detail: human-readable extra context.

    Output JSON line punya field tambahan `event_type`, `security=true` —
    aggregator bisa filter `{security="true"}` tanpa parse msg.
    """
    sec_logger = logging.getLogger("app.security")
    extra: dict[str, Any] = {
        "event_type": event_type,
        "security": True,
        "detail": detail[:500],  # bounded — avoid log injection
    }
    if user_id is not None:
        extra["actor_user_id"] = str(user_id)
    if tenant_id is not None:
        extra["actor_tenant_id"] = str(tenant_id)
    if request is not None:
        try:
            extra["client_ip"] = getattr(request.state, "client_ip", "-")
            extra["http_path"] = request.url.path
        except Exception:
            sec_logger.exception("gagal extract request.client_ip / http_path dari request.state")
    sec_logger.warning("security_event type=%s", event_type, extra=extra)

    # FASE 5 Sprint 2 — also increment Prometheus counter so SOC alerts
    # (rate>10/menit, dll) can fire dari `flipus_security_events_total`
    # tanpa parse log. Lazy import untuk avoid circular at module load
    # (logger.py is imported very early by app.main).
    try:
        from app.core.metrics import record_security_event
        # outcome derived from event_type prefix: "login_*" / "tenant_*" / dll.
        # Heuristik: kalau constanta ada di whitelist -> "ok" (logged, bukan
        # attack). Pemantauan real attack dilakukan via alert rule di
        # Prometheus / Loki, BUKAN dari label outcome.
        outcome = "ok"
        record_security_event(event_type, outcome=outcome)
    except Exception:
        # Metrics are best-effort — never let a missing prometheus_client
        # break the security log line.
        sec_logger.exception("record_security_event gagal; security log line sudah ditulis, metrics skipped")


# Konstanta event_type (pakai konstanta, bukan free string, untuk konsistensi
# filter di alert rule / dashboard).
SEC_EVENT_TENANT_SCOPE_VIOLATION = "tenant_scope_violation"
SEC_EVENT_LOGIN_FAILURE = "login_failure"
SEC_EVENT_2FA_FAILURE = "2fa_failure"
SEC_EVENT_PII_DECRYPT_FAILURE = "pii_decrypt_failure"
SEC_EVENT_RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
