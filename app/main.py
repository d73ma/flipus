from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings

from app.api.v1 import auth, onboarding, scanner, reports, sync, dashboard, register, master, users, admin, agregat, tenants, kuitansi, twofa, notifications, demo, wa_input, quick_input, pengeluaran, pengeluaran_ocr, pengeluaran_wa, laporan_gabungan, m8_managed

app = FastAPI(
    title="FLIPUS v1.3 — UKIKT",
    version="1.3.0",
    description="""
# FLIPUS — Sistem Akuntansi Jemaat Otomatis

**FLIPUS** (Financial Ledger & Integrated Perpuluhan Umbrella System) adalah
sistem digital untuk mengelola perpuluhan dan persembahan jemaat GMAHK
Uni Konferens Indonesia Kawasan Timur (UKIKT).

## Fitur Utama

- 📸 **OCR Amplop** — Baca nominal otomatis dari foto amplop (Gemini AI)
- 📊 **Agregat Dashboard** — Per minggu, per jemaat, per misi, per uni
- 📄 **PDF Generation** — Laporan resmi dengan header Uni/Misi/Jemaat
- 💬 **WhatsApp Integration** — Auto-thanks per kuitansi, blast mingguan ke Pendeta
- 🔒 **Security** — JWT auth, Fernet PII encryption, tenant signature
- 💾 **Backup & Restore** — Auto-backup harian, retention 7 file
- 👥 **5 Role Support** — Bendahara, Ketua, Pendeta, Auditor Misi, Admin Uni

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy 2.0 + APScheduler
- **Frontend:** Vite + React 18 + TypeScript + Tailwind
- **Database:** SQLite (default) / PostgreSQL (optional)
- **AI:** Google Gemini Vision untuk OCR
- **WA Gateway:** Fonnte (https://fonnte.com)

## API Conventions

- **Base URL:** `/api/v1/`
- **Auth:** Bearer JWT token di header `Authorization`
- **Pagination:** `page` + `per_page` query params (default 50)
- **Date format:** ISO 8601 (`YYYY-MM-DD`)
    """,
    terms_of_service="https://flipus.local/terms",
    contact={
        "name": "Jerry Mauri",
        "email": "support@flipus.local",
        "url": "https://flipus.local",
    },
    license_info={
        "name": "UKIKT Internal License",
        "url": "https://flipus.local/license",
    },
    openapi_tags=[
        {"name": "Auth", "description": "Login, logout, JWT, forgot-password"},
        {"name": "Onboarding", "description": "Tenant registration (legacy)"},
        {"name": "Scanner", "description": "OCR batch upload + save batch ke DB"},
        {"name": "Reports", "description": "Laporan mingguan, summary, sabat-info, blast PDF"},
        {"name": "Sync", "description": "Sync anonymized payloads ke Kantor Misi / Uni"},
        {"name": "Dashboard", "description": "Sabat-info + manual kuitansi submit"},
        {"name": "Register (Public)", "description": "Self-service registrasi Pendeta/Auditor/Admin"},
        {"name": "Master Data", "description": "Uni, Misi, seed"},
        {"name": "User Management", "description": "List & deactivate users (RBAC)"},
        {"name": "Admin (Jerry-only)", "description": "Backup, restore, audit logs, reset"},
        {"name": "Agregat Dashboards", "description": "Read-only agregat per tenant/misi/uni"},
        {"name": "Tenant Management (SaaS)", "description": "Resolve, profile, status, plan (Tahap 20)"},
        {"name": "Kuitansi Search & Export", "description": "Advanced filtering + CSV/Excel export (Tahap 22)"},
        {"name": "2FA / TOTP (Tahap 23)", "description": "Two-factor authentication setup + login flow"},
        {"name": "Notifications (Tahap 24)", "description": "In-app notification center — bell icon + real-time events"},
    ],
    swagger_ui_parameters={
        "deepLinking": True,
        "displayRequestDuration": True,
        "filter": True,
        "showExtensions": True,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()
    ] or ["http://localhost:5173"],
    # LAN origins (192.168.x.x, 10.x.x.x, 172.16-31.x.x) — untuk demo offline
    # multi-device di Wi-Fi yang sama. Hardcoded hostnames aman karena private range.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["Onboarding"])
app.include_router(scanner.router, prefix="/api/v1/scan", tags=["Scanner"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["Sync"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(register.router, prefix="/api/v1/register", tags=["Register (Public)"])
app.include_router(master.router, prefix="/api/v1/master", tags=["Master Data"])
app.include_router(users.router, prefix="/api/v1/users", tags=["User Management"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin (Jerry-only)"])
app.include_router(agregat.router, prefix="/api/v1/agregat", tags=["Agregat Dashboards"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["Tenant Management (SaaS)"])
app.include_router(kuitansi.router, prefix="/api/v1/kuitansi", tags=["Kuitansi Search & Export"])
app.include_router(twofa.router, prefix="/api/v1/auth", tags=["2FA / TOTP (Tahap 23)"])
app.include_router(notifications.router, prefix="/api/v1", tags=["Notifications (Tahap 24)"])
app.include_router(demo.router, prefix="/api/v1/demo", tags=["Demo Mode (Public)"])
app.include_router(wa_input.router, prefix="/api/v1", tags=["WA Input Bot (T94)"])
app.include_router(quick_input.router, prefix="/api/v1", tags=["Quick Input (v2.0 M1)"])
app.include_router(pengeluaran.router, prefix="/api/v1", tags=["Pengeluaran (v2.0 M5)"])
app.include_router(pengeluaran_ocr.router, prefix="/api/v1", tags=["Pengeluaran OCR (v2.0 M6)"])
app.include_router(pengeluaran_wa.router, prefix="/api/v1", tags=["Pengeluaran WA Bot (v2.0 M6)"])
app.include_router(laporan_gabungan.router, prefix="/api/v1", tags=["Laporan Gabungan (v2.0 M7)"])
app.include_router(m8_managed.router, prefix="/api/v1", tags=["Managed Users + Void (v2.0 M8)"])

# === Static files (logos jemaat untuk landing page) ===
# Folder: storage/logos/*.svg (dibuat otomatis oleh seed_demo.py)
_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage")
if os.path.isdir(_STORAGE_DIR):
    app.mount("/storage", StaticFiles(directory=_STORAGE_DIR), name="storage")
    print(f"[static] /storage → {_STORAGE_DIR}")
else:
    os.makedirs(_STORAGE_DIR, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=_STORAGE_DIR), name="storage")
    print(f"[static] /storage created → {_STORAGE_DIR}")

# === Start scheduler (background) ===
from app.services.reset_scheduler import start_scheduler
try:
    reset_scheduler = start_scheduler()
except Exception:
    pass

# === Auto-create missing tables (idempotent) ===
# Beberapa tabel (sync_outbox dll) mungkin belum ter-create kalau
# schema migration belum dijalankan. Kita create_all() di startup supaya
# endpoint /v1/sync/* tidak crash. Aman kalau tabel sudah ada (SQLAlchemy no-op).
from app.core.database import Base, engine
try:
    Base.metadata.create_all(bind=engine)
    print("[startup] Base.metadata.create_all() OK")
except Exception as e:
    import sys as _sys
    print(f"[startup] create_all gagal: {e}", file=_sys.stderr)

@app.get("/")
def root():
    return {
        "status": "FLIPUS Active",
        "version": "1.2.0",
        "tier": "UKIKT (Uni Konferens Indonesia Kawasan Timur)",
        "security": "AES-Fernet + JWT + Tenant Signature",
        "docs": "/docs",
        "redoc": "/redoc",
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.1.0"}
