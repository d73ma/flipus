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
import sys
import time
import uuid
from typing import Any, Dict, Optional


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
    request_id: Optional[str] = None,
    tenant_id: Optional[Any] = None,
    user_id: Optional[Any] = None,
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


def get_request_context() -> Dict[str, str]:
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

        payload: Dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
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
    level: Optional[str] = None,
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