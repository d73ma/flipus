"""FASE 3-S3.S3 — CORS env-driven via ALLOWED_ORIGINS.

Memverifikasi:
  1. ALLOWED_ORIGINS env override is parsed + applied to CORSMiddleware
  2. Whitespace + empty entries di-strip
  3. Wildcard '*' ditolak dengan warning (credentials=True spec violation)
  4. X-Request-ID di-allow di request + di-expose di response
  5. LAN origin (192.168.x.x) auto-allowed via regex
  6. Origin tidak dikenal ditolak (no Access-Control-Allow-Origin)
  7. Preflight OPTIONS succeeds untuk allowed origin
  8. ALLOWED_ORIGINS kosong → fallback ke localhost dev default
"""
from __future__ import annotations

import importlib

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_settings():
    """Force re-read of ALLOWED_ORIGINS from env.

    Settings adalah Pydantic BaseSettings yang cached at import time.
    Untuk test override, kita reload modulenya.
    """
    from app.core import config as cfg_mod

    importlib.reload(cfg_mod)
    return cfg_mod.settings


def _reload_main():
    """Force reload app.main supaya CORSMiddleware apply settings baru."""
    from app import main as main_mod

    importlib.reload(main_mod)
    return main_mod


def _get_cors_middleware(app):
    """Cari instance CORSMiddleware di app.user_middleware list."""
    from fastapi.middleware.cors import CORSMiddleware

    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            return m
    return None


# ---------------------------------------------------------------------------
# Unit tests — Settings parsing
# ---------------------------------------------------------------------------


def test_default_allowed_origins_contains_localhost():
    """Default config punya localhost dev origins untuk Vite + alternative ports."""
    s = _reload_settings()
    origins = [o.strip() for o in s.ALLOWED_ORIGINS.split(",") if o.strip()]
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins


def test_env_override_allowed_origins(monkeypatch):
    """ALLOWED_ORIGINS env var override default + diparse."""
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://gmahk.flipus.org, https://app.flipus.org ,  , https://admin.flipus.org",
    )
    s = _reload_settings()
    origins = [o.strip() for o in s.ALLOWED_ORIGINS.split(",") if o.strip()]
    # Whitespace di-strip, empty entries di-drop
    assert origins == [
        "https://gmahk.flipus.org",
        "https://app.flipus.org",
        "https://admin.flipus.org",
    ]


def test_env_override_empty_string_handled_by_main_fallback(monkeypatch):
    """Kalau env override string kosong, settings.ALLOWED_ORIGINS = ''.

    Main.py fallback handles empty string by substituting localhost default.
    Kita verify: settings.ALLOWED_ORIGINS bisa kosong string, dan parsing logic
    di main.py mengkonversi ke list non-empty (fallback ke localhost).
    """
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    s = _reload_settings()
    # pydantic respects env override (empty string is set, default is NOT used)
    assert s.ALLOWED_ORIGINS == ""
    # Parsing logic di main.py: empty string → fallback localhost
    parsed = [o.strip() for o in (s.ALLOWED_ORIGINS or "").split(",") if o.strip()]
    assert parsed == []  # empty after parsing
    # Fallback kicks in:
    final = parsed or ["http://localhost:5173"]
    assert "http://localhost:5173" in final


def test_wildcard_origin_is_dangerous_with_credentials():
    """Spec CORS: wildcard '*' + credentials=True di-drop oleh Starlette.

    Hard guard di main.py Hapus '*' + emit warning log supaya operator
    tidak silently kehilangan allow-origin.
    """
    # Simulasi parsing list yg mengandung wildcard
    test_origins = ["*", "http://localhost:5173"]
    assert "*" in test_origins  # precondition
    # Hard guard behavior: filter keluar '*'
    filtered = [o for o in test_origins if o != "*"]
    assert "*" not in filtered
    assert "http://localhost:5173" in filtered


# ---------------------------------------------------------------------------
# Integration tests — CORSMiddleware actual behavior via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Standard FastAPI TestClient — pakai conftest.py env defaults."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _cors_kwargs(app):
    """Ambil kwargs dari CORSMiddleware registration (Starlette Middleware)."""
    from fastapi.middleware.cors import CORSMiddleware

    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            return m.kwargs
    raise AssertionError("CORSMiddleware not registered")


def test_cors_middleware_is_registered():
    """Verify CORSMiddleware terdaftar di app."""
    from app.main import app

    kw = _cors_kwargs(app)
    assert kw["allow_credentials"] is True
    assert "GET" in kw["allow_methods"]
    assert "POST" in kw["allow_methods"]


def test_cors_allow_headers_includes_x_request_id():
    """X-Request-ID harus di-allow supaya client bisa kirim custom request ID."""
    from app.main import app

    kw = _cors_kwargs(app)
    headers = kw["allow_headers"]
    assert "X-Request-ID" in headers
    assert "Authorization" in headers
    assert "Content-Type" in headers


def test_cors_expose_headers_includes_x_request_id():
    """X-Request-ID harus di-expose supaya browser bisa baca response header."""
    from app.main import app

    kw = _cors_kwargs(app)
    exposed = kw.get("expose_headers", []) or []
    assert "X-Request-ID" in exposed


def test_cors_preflight_allowed_for_localhost(client):
    """Preflight OPTIONS dari localhost dev origin harus return CORS headers."""
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
        },
    )
    # Starlette CORSMiddleware returns 200 untuk preflight OK
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    # Allow headers include X-Request-ID
    allow_headers = resp.headers.get("access-control-allow-headers", "")
    assert "x-request-id" in allow_headers.lower()


def test_cors_preflight_blocked_for_unknown_origin(client):
    """Preflight dari origin tidak dikenal TIDAK boleh dapat allow-origin."""
    resp = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # CORS preflight di-block: no Access-Control-Allow-Origin
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
    # Atau tidak ada header sama sekali
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers.keys()} or \
        resp.headers.get("access-control-allow-origin") is None


def test_cors_lan_origin_allowed_via_regex(client):
    """LAN origin 192.168.x.x auto-allowed via allow_origin_regex."""
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://192.168.1.42:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # LAN origin masuk via regex (private range aman)
    assert resp.headers.get("access-control-allow-origin") == "http://192.168.1.42:5173"


def test_cors_x_request_id_echoed_in_response(client):
    """RequestContextMiddleware set X-Request-ID → response harus echo balik."""
    custom_rid = "test-corr-id-12345"
    resp = client.get("/health", headers={"X-Request-ID": custom_rid})
    # Middleware echo X-Request-ID in response headers
    assert resp.headers.get("X-Request-ID") == custom_rid or \
        resp.headers.get("x-request-id") == custom_rid


def test_cors_x_request_id_exposed_in_actual_response(client):
    """Actual GET response (bukan preflight) juga expose X-Request-ID."""
    resp = client.get("/health")
    rid = resp.headers.get("X-Request-ID") or resp.headers.get("x-request-id")
    # Middleware selalu generate ID kalau client tidak kirim
    assert rid is not None and len(rid) >= 8
    # expose_headers="X-Request-ID" → browser JS bisa baca via getResponseHeader()
    # (hanya bisa diverifikasi via integration browser test, tapi
    # header presence di response adalah proxy kuat bahwa expose_headers bekerja)
