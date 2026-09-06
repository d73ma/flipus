# FLIPUS API Reference

> **Version**: 2.0 (FASE 3 Sprint 4 — OpenAPI tags standardized)
> **Base URL**: `/api/v1`
> **OpenAPI schema**: `GET /openapi.json` · **Swagger UI**: `GET /docs` · **ReDoc**: `GET /redoc`
> **Status**: 104 routes · 39 OpenAPI tags · all routes require authentication except `Demo`, `Register (Public)`, and `Auth/login`

---

## 1. Ringkasan

FLIPUS API adalah RESTful JSON API yang melayani aplikasi **Sabbath Ledger** (frontend Vite/React) dan integrasi eksternal (WhatsApp bot, scheduler, OCR service). Semua endpoint berada di bawah prefix `/api/v1` dan di-mount dari `app/api/v1/*.py`.

| Statistik | Nilai |
|---|---|
| Total route di `/api/v1/*` | **104** |
| Total router file | 22 |
| Unique OpenAPI tag | **39** |
| HTTP method | `GET` · `POST` · `PUT` · `PATCH` · `DELETE` |
| Auth | JWT (HS256, python-jose) — header `Authorization: Bearer <token>` |
| Content-Type | `application/json` (kecuali upload: `multipart/form-data`) |
| Rate limit | slowapi — default 60 req/menit per IP (override per-route tersedia) |

---

## 2. OpenAPI Tags — Indeks

Setiap route dikelompokkan berdasarkan **fungsi bisnis** lewat parameter `tags=[...]` di dekorator `@router.<method>(...)`. Daftar 39 tag berikut adalah label resmi yang muncul di Swagger UI dropdown.

### 2.1 Autentikasi & Otorisasi

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Auth` | `auth.py` | 5 | Login, refresh token, logout, change password, forgot password |
| `2FA` | `twofa.py` | 6 | TOTP setup/verify/disable, backup codes, 2FA login (Tahap 23) |
| `Register (Public)` | `register.py` | 3 | Self-service register pendeta/auditor/admin (tanpa auth) |
| `Onboarding` | `onboarding.py` | 1 | Register tenant baru (multi-organisasi SaaS) |

### 2.2 Manajemen Pengguna & Tenant

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Users` | `users.py` | 2 | CRUD user dalam tenant aktif |
| `User Management` | `users.py` | 2 | Invite, role assign (managed oleh admin tenant) |
| `Tenants` | `tenants.py` | 12 | CRUD tenant, branding, logo, plan, status (SaaS admin) |
| `Tenant Management (SaaS)` | `tenants.py` | 12 | Resolve tenant by identifier, current tenant info |
| `Managed` | `m8_managed.py` | 3 | Cross-cutting: user invite + void kuitansi/pengeluaran (v2.0 M8) |

### 2.3 Domain Inti — Kuitansi (Penerimaan)

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Kuitansi` | `kuitansi.py` | 5 | Search, filter, export, PDF, recompute porsi |
| `QuickInput` | `quick_input.py` | 2 | Form input cepat kuitansi (v2.0 M1) |
| `Dashboard` | `dashboard.py` | 6 | Sabat info, kuitansi approve/reject/pending/rejected |

### 2.4 Domain Inti — Pengeluaran (Expense)

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Pengeluaran` | `pengeluaran.py` | 11 | CRUD, submit, approve-ketua/pendeta, reject, rekap |
| `Pengeluaran OCR (v2.0 M6)` | `pengeluaran_ocr.py` | 2 | OCR batch upload + save (receipt-to-expense) |
| `Pengeluaran WA Bot (v2.0 M6)` | `pengeluaran_wa.py` | 2 | Inbound dari WhatsApp bot + reset state |

### 2.5 Agregat, Laporan & Reports

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Agregat` | `agregat.py` | 6 | Tenant/misi/uni/sabat-ini/YTD/chart mingguan |
| `Agregat Dashboards` | `agregat.py` | 6 | Sama dengan Agregat — alias untuk UI grouping |
| `Laporan` | `laporan_gabungan.py` | 3 | Laporan gabungan per rekap mingguan (PDF + auditor blast) |
| `Reports` | `reports.py` | 5 | Sabat info, mingguan, summary, blast-weekly, keuangan |

### 2.6 Master Data & Notifikasi

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Master` | `master.py` | 5 | Uni, misi, seed, persentase porsi (CRUD) |
| `Master Data` | `master.py` | 5 | Alias untuk UI grouping |
| `Notifications` | `notifications.py` | 6 | List, unread-count, mark-read, read-all, delete, clear-all |

### 2.7 Integrasi Eksternal

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `WhatsApp` | `wa_input.py` | 5 | WA bot integration (T94) — text/photo inbound |
| `WA Input Bot (T94)` | `wa_input.py` | 5 | Alias deskriptif untuk WA bot |
| `Scanner` | `scanner.py` | 2 | Scan batch upload + save-batch (OCR pipeline) |
| `Sync` | `sync.py` | 2 | Offline → online sync (queue-based) |
| `Admin` | `admin.py` | 7 | Fonnte device status, trigger reset/backup, recompute porsi (Jerry-only) |

### 2.8 Demo & Utilitas

| Tag | Modul | Routes | Keterangan |
|---|---|---:|---|
| `Demo` | `demo.py` | 3 | Demo mode (login-as-role, info, tenants) — **tanpa auth** |
| `Demo Mode (Public)` | `demo.py` | 3 | Alias untuk visibility |

---

## 3. Konvensi Response

### 3.1 Success

```json
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: <uuid>

{
  "data": { /* payload */ },
  "meta": { "page": 1, "total": 42 }
}
```

### 3.2 Error

```json
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json
X-Request-ID: <uuid>

{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "field 'nominal' must be positive",
    "details": [ /* Pydantic errors */ ]
  }
}
```

Kode error standar: `400` (bad request) · `401` (unauthorized) · `403` (forbidden) · `404` (not found) · `409` (conflict) · `422` (validation) · `429` (rate limited) · `500` (internal).

### 3.3 Pagination

Endpoint list mendukung query: `?page=1&page_size=20&sort=-created_at&q=keyword`. Response memuat `meta.total` untuk total record dan `meta.pages` untuk total halaman.

---

## 4. Autentikasi

### 4.1 Alur Login

```
POST /api/v1/auth/login        → access_token (15 min) + refresh_token (7 days)
POST /api/v1/auth/refresh      → new access_token (refresh_token di body)
POST /api/v1/auth/logout       → invalidate refresh_token
```

### 4.2 Two-Factor Authentication (TOTP)

```
GET  /api/v1/auth/2fa/status         → {enabled, has_backup_codes}
POST /api/v1/auth/2fa/setup          → QR + secret
POST /api/v1/auth/2fa/verify         → confirm code (activate)
POST /api/v1/auth/2fa/login          → complete login dengan TOTP code
POST /api/v1/auth/2fa/disable        → turn off (butuh password + TOTP)
POST /api/v1/auth/2fa/backup-codes   → regenerate 10 backup codes
```

### 4.3 Header Wajib

| Header | Wajib | Keterangan |
|---|:-:|---|
| `Authorization` | ✅ | `Bearer <jwt_access_token>` |
| `Content-Type` | ✅ | `application/json` atau `multipart/form-data` (upload) |
| `X-Request-ID` | optional | UUID v4 untuk tracing; di-echo di response |
| `X-Admin-Token` | ⚠️ | Hanya untuk endpoint `Admin/*` (Jerry-only) |

---

## 5. Multi-Tenant Isolation

Setiap request di-resolve ke `tenant_id` dari JWT claim (`tid`). Query database **wajib** filter `WHERE tenant_id = :tid` kecuali untuk endpoint `Admin/*` (SaaS admin) dan `Tenants/*` (CRUD tenant itu sendiri).

Lihat [`FASE2_VALIDASI_AKUNTANSI.md`](../FASE2_VALIDASI_AKUNTANSI.md) untuk hasil audit integrity accounting per tenant.

---

## 6. Rate Limiting

| Scope | Limit | Override |
|---|---|---|
| Global | 60 req/menit/IP | `slowapi` decorator |
| `auth/login` | 5 req/menit/IP | stricter (anti-brute force) |
| `auth/2fa/*` | 10 req/menit/IP | per-user |
| Upload (OCR/scan) | 20 req/jam/IP | stricter (resource heavy) |

Response saat rate-limited: `HTTP 429` + `Retry-After` header.

---

## 7. Modul Router → Tag Mapping

| File | Route count | Primary tag(s) |
|---|---:|---|
| `app/api/v1/admin.py` | 7 | `Admin` |
| `app/api/v1/agregat.py` | 6 | `Agregat` |
| `app/api/v1/auth.py` | 5 | `Auth` |
| `app/api/v1/dashboard.py` | 6 | `Dashboard` |
| `app/api/v1/demo.py` | 3 | `Demo` |
| `app/api/v1/kuitansi.py` | 5 | `Kuitansi` |
| `app/api/v1/laporan_gabungan.py` | 3 | `Laporan` |
| `app/api/v1/m8_managed.py` | 3 | `Managed` |
| `app/api/v1/master.py` | 5 | `Master` |
| `app/api/v1/notifications.py` | 6 | `Notifications` |
| `app/api/v1/onboarding.py` | 1 | `Onboarding` |
| `app/api/v1/pengeluaran.py` | 11 | `Pengeluaran` |
| `app/api/v1/pengeluaran_ocr.py` | 2 | `Pengeluaran OCR (v2.0 M6)` |
| `app/api/v1/pengeluaran_wa.py` | 2 | `Pengeluaran WA Bot (v2.0 M6)` |
| `app/api/v1/quick_input.py` | 2 | `QuickInput` |
| `app/api/v1/register.py` | 3 | `Register` |
| `app/api/v1/reports.py` | 5 | `Reports` |
| `app/api/v1/scanner.py` | 2 | `Scanner` |
| `app/api/v1/sync.py` | 2 | `Sync` |
| `app/api/v1/tenants.py` | 12 | `Tenants` |
| `app/api/v1/twofa.py` | 6 | `2FA` |
| `app/api/v1/users.py` | 2 | `Users` |
| `app/api/v1/wa_input.py` | 5 | `WhatsApp` |
| **Total** | **104** | **39 unique tags** |

---

## 8. Perubahan Versi

### 2.0 (FASE 3 Sprint 4 — 2026-09-02)

- **R2**: Semua 104 route sekarang memiliki parameter `tags=[...]` di dekorator `@router.<method>`.
- Sebelumnya: hanya `notifications.py` dan `sync.py` yang punya tag (lewat `APIRouter(tags=...)`).
- Sekarang: 39 tag terstandarisasi untuk grouping di Swagger UI dan dokumentasi generator.

### 1.x (sebelum FASE 3)

- Tag hanya di-inherit dari `APIRouter(tags=...)` constructor (mayoritas file kosong).
- Swagger UI menampilkan semua 104 route dalam satu flat list tanpa grouping.

---

## 9. Cara Generate Docs

OpenAPI schema auto-generated oleh FastAPI:

```bash
# Dump schema
curl http://localhost:8000/openapi.json | jq . > openapi.json

# Swagger UI (interaktif)
open http://localhost:8000/docs

# ReDoc (read-only)
open http://localhost:8000/redoc
```

Untuk export ke Postman/Insomnia: import `openapi.json` di tool tersebut.
