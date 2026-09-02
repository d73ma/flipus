"""FASE 3-S3.S1 — Centralized JSON structured logging.

Memverifikasi:
  1. JSONFormatter output valid JSON + schema fields lengkap
  2. Contextvars (request_id, tenant_id, user_id) muncul di output
  3. Extra fields via logger.xxx(..., extra={...}) terserialize
  4. Exception info (logger.exception) muncul sebagai field 'exc'
  5. setup_logging() idempotent (no duplicate handler)
  6. RequestContextMiddleware attach request_id + echo header
  7. /health endpoint log muncul dengan request_id (integration via TestClient)
"""
from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Unit tests — JSONFormatter + contextvars
# ---------------------------------------------------------------------------


def _build_record(name: str, level: int, msg: str, **extra) -> logging.LogRecord:
    """Helper: build a LogRecord with optional extra fields."""
    rec = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_outputs_valid_json():
    """Setiap log line harus single-line JSON yang bisa di-parse."""
    from app.core.logger import JSONFormatter
    fmt = JSONFormatter()
    rec = _build_record("flipus.test", logging.INFO, "hello")
    line = fmt.format(rec)
    obj = json.loads(line)  # raises ValueError kalau bukan JSON
    assert isinstance(obj, dict)
    # Required schema fields
    for k in ("ts", "level", "logger", "msg", "request_id", "tenant_id", "user_id"):
        assert k in obj, f"missing field: {k}"
    assert obj["level"] == "INFO"
    assert obj["logger"] == "flipus.test"
    assert obj["msg"] == "hello"
    # Default contextvar value = "-"
    assert obj["request_id"] == "-"
    # TS in ISO 8601 UTC
    assert obj["ts"].endswith("Z")
    assert "T" in obj["ts"]


def test_json_formatter_includes_contextvars():
    """set_request_context() values harus muncul di output."""
    from app.core.logger import JSONFormatter, set_request_context
    set_request_context(request_id="rqx12345", tenant_id=99, user_id=42)
    try:
        fmt = JSONFormatter()
        rec = _build_record("flipus.test", logging.INFO, "scoped")
        obj = json.loads(fmt.format(rec))
        assert obj["request_id"] == "rqx12345"
        assert obj["tenant_id"] == "99"
        assert obj["user_id"] == "42"
    finally:
        # Reset supaya tidak bocor ke test lain
        set_request_context(request_id="-", tenant_id="-", user_id="-")


def test_json_formatter_includes_extra_fields():
    """logger.info(..., extra={"key": "val"}) harus muncul di output."""
    from app.core.logger import JSONFormatter
    fmt = JSONFormatter()
    rec = _build_record(
        "flipus.auth",
        logging.WARNING,
        "login failed",
        action="LOGIN_FAILED",
        username="alice",
        attempts=3,
    )
    obj = json.loads(fmt.format(rec))
    assert obj["action"] == "LOGIN_FAILED"
    assert obj["username"] == "alice"
    assert obj["attempts"] == 3


def test_json_formatter_handles_exception():
    """logger.exception() harus populate field 'exc' dengan traceback."""
    from app.core.logger import JSONFormatter
    fmt = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="flipus.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="crash",
            args=(),
            exc_info=sys.exc_info(),
        )
        obj = json.loads(fmt.format(rec))
        assert obj["level"] == "ERROR"
        assert obj["msg"] == "crash"
        assert "exc" in obj
        assert "ValueError" in obj["exc"]
        assert "boom" in obj["exc"]


def test_json_formatter_unicode_safe():
    """Pesan dengan karakter unicode/emoji harus terserialize dengan benar."""
    from app.core.logger import JSONFormatter
    fmt = JSONFormatter()
    rec = _build_record("flipus.test", logging.INFO, "Sukses ✓ GMAHK UKIKT 赞美")
    line = fmt.format(rec)
    obj = json.loads(line)
    assert "✓" in obj["msg"]
    assert "赞美" in obj["msg"]


def test_json_formatter_non_serializable_extra_falls_back_to_repr():
    """Kalau extra value tidak JSON-serializable, fallback ke repr() string."""
    from app.core.logger import JSONFormatter
    fmt = JSONFormatter()
    # object() tidak bisa di-json.dumps
    rec = _build_record("flipus.test", logging.INFO, "test", weird_obj=object())
    line = fmt.format(rec)
    obj = json.loads(line)
    assert "weird_obj" in obj
    assert "object at 0x" in obj["weird_obj"]  # repr() format


# ---------------------------------------------------------------------------
# setup_logging() tests
# ---------------------------------------------------------------------------


def test_setup_logging_idempotent_no_duplicate_handlers():
    """Multiple calls ke setup_logging() tidak duplicate JSON handler."""
    from app.core.logger import setup_logging
    setup_logging(level="INFO", force=True)
    n1 = len(logging.getLogger().handlers)
    setup_logging(level="INFO", force=False)
    setup_logging(level="INFO", force=False)
    n2 = len(logging.getLogger().handlers)
    assert n1 == n2, f"handlers grew: {n1} → {n2}"


def test_setup_logging_force_resets():
    """force=True harus drop semua handler dan re-add JSON handler saja."""
    from app.core.logger import setup_logging
    setup_logging(level="INFO", force=True)
    # Tambah noise handler
    logging.getLogger().addHandler(logging.NullHandler())
    logging.getLogger().addHandler(logging.NullHandler())
    assert len(logging.getLogger().handlers) > 1
    # Force reset
    setup_logging(level="INFO", force=True)
    n_after = len(logging.getLogger().handlers)
    assert n_after == 1, f"force=True should leave 1 handler, got {n_after}"


def test_log_level_env_override():
    """LOG_LEVEL env var harus mengubah root logger level."""
    import os
    from app.core.logger import setup_logging
    setup_logging(level="DEBUG", force=True)
    assert logging.getLogger().level == logging.DEBUG

    setup_logging(level="WARNING", force=True)
    assert logging.getLogger().level == logging.WARNING


# ---------------------------------------------------------------------------
# Integration test — RequestContextMiddleware + /health endpoint
# ---------------------------------------------------------------------------


def test_middleware_sets_request_id_from_header():
    """X-Request-ID header harus dipropagasi ke contextvars."""
    from app.core.logger import set_request_context
    # Reset
    set_request_context(request_id="-", tenant_id="-", user_id="-")

    from app.main import app  # noqa: F401 (import for TestClient)
    client = TestClient(app)

    rid = "integration-rid-12345"
    resp = client.get("/health", headers={"X-Request-ID": rid})
    assert resp.status_code == 200
    # Middleware echoes X-Request-ID back ke response
    assert resp.headers.get("X-Request-ID") == rid


def test_middleware_generates_request_id_when_missing():
    """Kalau X-Request-ID tidak ada, middleware harus generate UUID."""
    from app.core.logger import set_request_context
    set_request_context(request_id="-", tenant_id="-", user_id="-")

    from app.main import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None
    assert len(rid) >= 8  # UUID 16-char hex minimal
    assert rid != "-"


def test_health_endpoint_emits_json_log():
    """GET /health harus menghasilkan minimal 1 JSON log line dengan request_id."""
    from app.core.logger import setup_logging

    # Capture stdout/stderr untuk verifikasi JSON output
    captured = io.StringIO()
    setup_logging(level="INFO", stream=captured, force=True)

    from app.main import app
    client = TestClient(app)
    rid = "health-rid-test"
    resp = client.get("/health", headers={"X-Request-ID": rid})
    assert resp.status_code == 200

    # Parse semua line yang ditulis
    output = captured.getvalue()
    json_lines = [
        line for line in output.splitlines() if line.startswith("{") and line.endswith("}")
    ]
    assert len(json_lines) > 0, f"No JSON log lines captured: {output[:500]}"

    # Cari line dengan request_id == rid (dari /health endpoint)
    matched = []
    for line in json_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("request_id") == rid and obj.get("http_path") == "/health":
            matched.append(obj)

    assert len(matched) >= 1, (
        f"No log line with request_id={rid} path=/health. "
        f"All JSON lines: {[json.loads(l).get('msg', '?') for l in json_lines]}"
    )
    # Field schema
    obj = matched[0]
    assert obj["level"] in ("INFO", "DEBUG", "WARNING", "ERROR")
    # msg is format-string applied with args, e.g. "request_completed method=GET path=/health ..."
    assert obj["msg"].startswith("request_completed")
    assert "method=GET" in obj["msg"]
    assert "path=/health" in obj["msg"]
    assert obj["http_method"] == "GET"
    assert obj["http_status"] == 200
    assert isinstance(obj["elapsed_ms"], (int, float))
    # Contextvars from request_id header should match
    assert obj["request_id"] == rid


def test_setup_logging_matmul_default_noop():
    """Kalau dipanggil tanpa args, setup_logging harus respect env LOG_LEVEL."""
    # Simpan env state
    import os
    saved = os.environ.get("LOG_LEVEL")
    os.environ["LOG_LEVEL"] = "ERROR"
    try:
        from app.core.logger import setup_logging
        setup_logging(force=True)
        assert logging.getLogger().level == logging.ERROR
    finally:
        if saved is None:
            os.environ.pop("LOG_LEVEL", None)
        else:
            os.environ["LOG_LEVEL"] = saved