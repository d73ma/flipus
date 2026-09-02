# FLIPUS — Sistem Akuntansi Jemaat Otomatis

> **Financial Ledger & Integrated Perpuluhan Umbrella System**
> GMAHK Uni Konferens Indonesia Kawasan Timur (UKIKT) — 2026

[![Version](https://img.shields.io/badge/version-1.3.0-green.svg)]()
[![License](https://img.shields.io/badge/license-UKIKT%20Internal-blue.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![React](https://img.shields.io/badge/react-18-blue.svg)]()

---

## � Quick Start

### Opsi 1: Docker (Recommended)

```bash
# 1. Copy env file
cp .env.example .env
# Edit .env: isi SECRET_KEY, PII_ENCRYPTION_KEY, GEMINI_API_KEY, FONNTE_TOKEN

# 2. Generate secret keys
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "from cryptography.fernet import Fernet; print('PII_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

# 3. Start semua services
docker compose up -d

# Akses:
#   Frontend:  http://localhost
#   Backend:   http://localhost/api
#   Swagger:   http://localhost/api/docs
#   Redoc:     http://localhost/api/redoc
```

### Opsi 2: Manual (Development)

```bash
# Backend
cd /Users/jerrymauri/Flipus
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (terminal baru)
cd /Users/jerrymauri/Flipus/frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## 🏗️ Arsitektur

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  React (5173)   │ ───> │  FastAPI (8000) │ ───> │  SQLite/PG DB   │
│  Vite + TS      │      │  + APScheduler  │      │  + Storage/     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                          │
        │                          ├──> Fonnte WA Gateway
        │                          └──> Gemini AI (OCR)
```

### Backend Stack
- **FastAPI** + **uvicorn** (4 workers)
- **SQLAlchemy 2.0** ORM
- **Pydantic** v2 validation
- **APScheduler** untuk cron jobs
- **python-jose** JWT
- **bcrypt** password hashing
- **cryptography** Fernet PII encryption
- **reportlab** PDF generation

### Frontend Stack
- **Vite** + **React 18** + **TypeScript**
- **React Router v6** (SPA routing)
- **Axios** HTTP client
- **Tailwind CSS** (Sabbath Ledger theme)
- **Code splitting** dengan lazy loading

---

## 🎯 5 Role Workflow

```
┌──────────────┐    upload foto     ┌─────────────────┐
│  Bendahara   │ ────────────────> │   OCR (Gemini)  │
│  (jemaat)    │                    └─────────────────┘
└──────┬───────┘                              │
       │ review + save                        │
       ▼                                      ▼
┌──────────────┐    auto-thanks     ┌─────────────────┐
│   Kuitansi   │ <──────────────── │  Fonnte WA      │
│   DB         │                    └─────────────────┘
└──────�───────┘
       │ blast mingguan (PDF)
       ▼
┌──────────────┐                  ┌─────────────────┐
│   Pendeta    │ ───────────────> │  Baca laporan   │
└──────────────┘                  └─────────────────┘

       ▲                                   ▲
       │ sync (anonymized)                │
       │                                   │
┌──────────────�                  ┌─────────────────┐
│   Auditor    │ <─────────────── │   Sync Outbox   │
│   Misi       │                  │   (per tenant)  │
└──────────────┘                  └─────────────────┘
       │
       │ roll up ke Uni
       ▼
┌──────────────┐
│   Admin Uni  │ — backup/restore/audit log
│   (Jerry)    │
└──────────────┘
```

---

## 📂 Struktur Direktori

```
/Users/jerrymauri/Flipus/
├── app/                          # Backend FastAPI
│   ├── api/v1/                   # 11 routers (auth, scanner, reports, etc)
│   ├── core/                     # config, db, security, cache
│   ├── models/                   # SQLAlchemy models
│   ├── services/                 # Business logic
│   ├── utils/                    # Helpers (nomor_kuitansi, sabat_counter, etc)
│   ├── ai_engine/                # OCR processor (Gemini)
│   └── main.py                   # FastAPI app entry
├── frontend/                     # React SPA
│   ├── src/
│   │   ├── pages/                # Dashboard pages
│   │   ├── components/           # Reusable (AgregatTable, Layout)
│   │   ├── lib/                  # auth, api (axios)
│   │   └── App.tsx
│   ├── vite.config.ts            # Code splitting
│   └── tailwind.config.js        # Sabbath Ledger theme
├── storage/
│   ├── temp/                     # Upload staging
│   ├── amplop_records/           # Foto amplop archived
│   ├── backups/                  # DB backups (auto-cleanup 7)
│   └── scripts/                  # CLI tools
├── docs/
│   └── USER_MANUAL.md            # User documentation
├── backend.Dockerfile            # Multi-stage backend image
├── frontend.Dockerfile           # Multi-stage frontend image
├── docker-compose.yml            # 3-service orchestration
├── nginx.conf                    # Reverse proxy + SPA fallback
├── .env.example                  # Environment template
├── requirements.txt              # Python deps
└── CHANGELOG.md                  # Version history
```

---

## 🚀 Production Deployment

```bash
# 1. Setup HTTPS (Let's Encrypt)
./storage/scripts/setup_https.sh yourdomain.com your@email.com

# 2. Migrate SQLite ke PostgreSQL (opsional, untuk multi-user)
PG_HOST=localhost PG_USER=flipus PG_PASSWORD=xxx \
    python3 -m storage.scripts.migrate_sqlite_to_postgres

# Update .env: DATABASE_URL_LOCAL=postgresql://flipus:xxx@postgres:5432/flipus

# 3. Run with Docker
docker compose up -d

# 4. Verify
curl http://localhost/api/health
```

---

## 🏢 Tahap 20 — Multi-Tenant SaaS Hardening (v1.3)

Setiap jemaat adalah **tenant independen** dengan identitas unik (slug),
siklus hidup (status), dan metadata pemilik. Sistem tetap menggunakan
**shared database + `tenant_id`** (sudah ada sejak v1.1), ditambah penguat:

### Tenant Identity & Lifecycle

| Field | Tipe | Keterangan |
|-------|------|------------|
| `slug` | String, unique | URL-safe identifier (auto-generated dari `nama_jemaat_lokal`) |
| `subdomain` | String, unique, nullable | Custom subdomain (opsional, e.g. `nataan.flipus.app`) |
| `plan` | Enum | `free` / `standard` / `premium` |
| `status` | Enum | `active` / `suspended` / `archived` |
| `owner_user_id` | FK → users | Primary contact / owner |
| `contact_email` | String | Admin email |
| `contact_phone` | String | Admin phone (non-WA) |

### Hardening Checklist

- ✅ `get_current_user` reject jika tenant `status != 'active'` (suspend → 403)
- ✅ Login menerima `tenant_slug` opsional; jika diberikan, HARUS match user.tenant_id
- ✅ Cross-tenant login attempt di-log ke `AuditLog` dengan action `CROSS_TENANT_BLOCKED_*`
- ✅ Forgot-password scope-able by `tenant_slug` (Tahap 20)
- ✅ Legacy tenant auto-backfill slug saat login pertama
- ✅ Slug generator dengan reserved-word protection (admin, api, dll)
- ✅ Tenant signature (legacy license guard) tetap berlaku

### Endpoint Baru (Tahap 20)

| Method | Path | Akses |
|--------|------|-------|
| GET | `/api/v1/tenants/resolve/{slug}` | Public (info-only) |
| GET | `/api/v1/tenants/me` | Authenticated (any role) |
| GET | `/api/v1/tenants` | ADMIN_UNI / AUDITOR_MISI |
| GET | `/api/v1/tenants/{id}` | ADMIN_UNI |
| PATCH | `/api/v1/tenants/{id}` | ADMIN_UNI (profile) |
| PATCH | `/api/v1/tenants/{id}/status` | ADMIN_UNI (suspend/activate) |
| PATCH | `/api/v1/tenants/{id}/plan` | ADMIN_UNI (free/standard/premium) |

### Frontend Changes

- `useAuth().tenant` sekarang expose `TenantInfo` (nama_jemaat, nama_uni, plan, status)
- Login bisa kirim `tenant_slug` (untuk white-label scenario)
- Navbar menampilkan `nama_jemaat + nama_uni` otomatis dari `/tenants/me`

### Test Coverage

Jalankan integration tests:

```bash
cd /Users/jerrymauri/Flipus
.venv/bin/python3 -m pytest tests/test_tenant_saas.py -v
```

Coverage:
- Slug generator (basic, reserved, collision)
- Tenant resolution by slug/subdomain
- Inactive tenant rejection (suspended/archived)
- Cross-tenant login attempt blocking
- Admin uni endpoints (list, status change, plan change)
- Self-service registrasi creates tenant dengan slug
- Legacy tenant slug auto-backfill

---

## 🎨 Tahap 21 — White-Label Branding (v1.3)

Setiap jemaat/admin uni dapat customize branding jemaat-nya:

| Field | Tipe | Default | Keterangan |
|-------|------|---------|------------|
| `logo_url` | file path | `null` | PNG/JPG/SVG ≤1MB, auto-resize 512px |
| `primary_color` | hex `#RRGGBB` | `#1B4332` | Header, tombol, aksen |
| `secondary_color` | hex `#RRGGBB` | `#F5EFE0` | Background halaman |
| `footer_text` | string ≤255 char | `null` | Footer PDF + WA message |

**Cara Pakai**:
1. Login sebagai ADMIN_UNI
2. Buka `/settings/branding`
3. Upload logo (drag & drop) + pilih preset warna / custom
4. Klik "Simpan Branding"

**Efek Branding**:
- Header app: warna primary_color, logo jemaat (jika ada)
- CSS variables `--tenant-primary` & `--tenant-secondary` di-inject otomatis
- PDF laporan mingguan: header + footer pakai warna + logo jemaat
- WhatsApp message: footer_text di-append ke pesan

**Reserved Slug** (tidak bisa dipakai tenant): `admin, api, www, app, static, docs, auth, register, login, logout, dashboard, health, system, master, backup, audit, tenant, tenants, root, support, help`

---

## 🔎 Tahap 22 — Advanced Search & Export (v1.3)

Pencarian kuitansi powerful dengan multiple filter + export ke CSV/Excel untuk analisis offline.

### Endpoint Baru

| Method | Path | Deskripsi |
|--------|------|-----------|
| GET | `/v1/kuitansi/search` | Advanced filter (date, tipe, nominal, nama, id_rekap) |
| GET | `/v1/kuitansi/export` | Stream CSV atau XLSX |
| GET | `/v1/kuitansi/filter-meta` | Aggregate stats (total, range, dll) |

### Filter yang Didukung

| Filter | Tipe | Keterangan |
|--------|------|------------|
| `date_from` | ISO date | Filter `tanggal_sabat >= date_from` |
| `date_to` | ISO date | Filter `tanggal_sabat <= date_to` |
| `tipe` | enum | `x` \| `pt` \| `khusus` \| `x_pt` \| `all_has_value` \| `kositng` |
| `nominal_min` | int | Filter `total_pemberian_angka >= nominal_min` |
| `nominal_max` | int | Filter `total_pemberian_angka <= nominal_max` |
| `nama` | string | LIKE search pada `nama_umat` (decrypted) |
| `id_rekap` | string | Exact match ke `id_rekap_mingguan` |
| `sort_by` | enum | `tanggal_sabat` \| `nominal` \| `created_at` |
| `sort_order` | enum | `asc` \| `desc` |
| `page` / `per_page` | int | Pagination (default 50, max 500) |

### Performance Indexes (Composite)

| Index | Kolom | Use Case |
|-------|-------|----------|
| `ix_kuitansi_tenant_tanggal` | (tenant_id, tanggal_sabat) | Date range filter |
| `ix_kuitansi_tenant_purged_tanggal` | (tenant_id, is_purged, tanggal_sabat) | Default query + date |
| `ix_kuitansi_tenant_nominal` | (tenant_id, total_pemberian_angka) | Nominal range |
| `ix_kuitansi_tenant_rekap` | (tenant_id, id_rekap_mingguan) | Per-rekap lookup |

### RBAC Scope Otomatis

| Role | Scope |
|------|-------|
| BENDAHARA / KETUA_KEUANGAN / PENDETA | Hanya jemaat sendiri |
| AUDITOR_MISI | Semua jemaat di misi |
| ADMIN_UNI | Semua jemaat di uni |

### Frontend UI

- `KuitansiSearchPanel.tsx` — reusable component
- Terpasang di BendaharaDashboard, AuditorDashboard, AdminDashboard
- Quick search box (nama) + collapsible filter panel
- Export buttons (CSV / XLSX) — download blob otomatis
- Pagination (25/50/100/250 per page)

### Audit Logging

Setiap search & export di-log ke `AuditLog`:
- `KUITANSI_SEARCH_user_X_filters=...`
- `KUITANSI_EXPORT_CSV_user_X_count_N`
- `KUITANSI_EXPORT_XLSX_user_X_count_N`

---

## 🛡️ Tahap 23 — Approval Workflow + 2FA / TOTP (v1.3)

Tutup 2 gap penting untuk production SaaS financial system: governance (approval) dan security (2FA).

### 23.1 — Approval Workflow

Setiap kuitansi harus melalui approval sebelum eligible untuk PDF / WA / agregat final.

**Kuitansi Status:**
| Status | Created by | Eligible untuk PDF/WA? | Description |
|--------|-----------|----------------------|-------------|
| `draft` | BENDAHARA | ❌ | Baru dibuat, awaiting Ketua approval |
| `finalized` | BENDAHARA → KETUA (via approve) / KETUA langsung | ✅ | Approved, locked, immutable |
| `rejected` | BENDAHARA → KETUA (via reject) | ❌ | Denied, dengan alasan |

**Default behavior:**
- BENDAHARA create → `status='draft'` (auto)
- KETUA_KEUANGAN create → `status='finalized'` langsung (sudah punya authority)
- Auto-thanks WA **HANYA** dikirim untuk kuitansi yang `finalized`
- PDF mingguan & WA blast hanya aggregate kuitansi `finalized`

**Endpoint baru:**
| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/v1/dashboard/kuitansi/{id}/approve` | KETUA_KEUANGAN, ADMIN_UNI | Approve draft → finalized |
| POST | `/v1/dashboard/kuitansi/{id}/reject` | KETUA_KEUANGAN, ADMIN_UNI | Reject dengan alasan (min 5 char) |
| GET | `/v1/dashboard/kuitansi/pending` | KETUA_KEUANGAN, ADMIN_UNI, BENDAHARA | List kuitansi awaiting approval |
| GET | `/v1/dashboard/kuitansi/rejected` | KETUA_KEUANGAN, ADMIN_UNI, BENDAHARA | List kuitansi rejected |

**`status_filter` parameter** (di `/v1/reports/mingguan`, `/v1/kuitansi/search`, `/v1/kuitansi/export`):
- `finalized` (default) — hanya approved
- `draft` — hanya awaiting
- `rejected` — yang ditolak
- `all` — semua

**Schema (`Kuitansi`):**
- `status` (String 20, default 'finalized', indexed)
- `created_by_user_id` (FK → users)
- `approved_by_user_id`, `approved_at`
- `rejected_by_user_id`, `rejected_at`, `rejected_reason`

### 23.2 — Two-Factor Authentication (TOTP / RFC 6238)

Setiap user (recommended: BENDAHARA, KETUA_KEUANGAN, ADMIN_UNI) bisa enable 2FA menggunakan Authenticator app.

**Flow login (2FA enabled):**
1. User submit username + password → dapat `partial_token` (5 min expiry)
2. User submit `partial_token` + 6-digit TOTP code → dapat full JWT
3. Atau: submit `username + password + totp_code` sekaligus dalam satu POST

**Backup Codes:**
- 10 single-use recovery codes di-generate saat enable
- Format: `ABC12-DEF34`
- Hash disimpan di DB (bcrypt)
- Counter di-decrement saat dipakai

**Endpoint baru (di bawah `/api/v1/auth/`):**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/2fa/status` | Cek status 2FA user |
| POST | `/2fa/setup` | Generate secret + QR code |
| POST | `/2fa/verify` | Verify first TOTP → enable 2FA + show backup codes |
| POST | `/2fa/disable` | Disable (require TOTP + password) |
| POST | `/2fa/backup-codes` | Regenerate backup codes (require TOTP) |
| POST | `/2fa/login` | Step 2: submit partial_token + TOTP code |

**Schema (`User`):**
- `is_2fa_enabled` (Boolean, default False)
- `totp_secret_encrypted` (Fernet-encrypted base32)
- `backup_codes_hashed` (JSON list bcrypt)
- `twofa_enabled_at`, `last_2fa_used_at`

**Library:** `pyotp==2.9.0` + `qrcode==7.4.2` (sudah di requirements.txt)

**Audit logging untuk 2FA:**
- `2FA_SETUP_INITIATED_user_X`
- `2FA_ENABLED_user_X`
- `2FA_DISABLED_user_X`
- `2FA_LOGIN_TOTP_user_X`
- `2FA_LOGIN_BACKUP_user_X_remaining_N`
- `2FA_BACKUP_CODES_REGENERATED_user_X`

---

## 🔔 Tahap 24 — Real-Time Notification Center (v1.3)

Tutup gap komunikasi workflow: user tidak perlu refresh halaman untuk tau ada event penting. Bell icon di header dengan badge unread + dropdown panel.

### Event Types

| Event | Trigger | Recipient | Icon |
|-------|---------|-----------|------|
| `KUITANSI_DRAFT_CREATED` | Bendahara POST kuitansi | Ketua Keuangan jemaat | 📝 |
| `KUITANSI_APPROVED` | Ketua approve draft | Bendahara (creator) + semua Admin Uni di uni | ✅ |
| `KUITANSI_REJECTED` | Ketua reject draft | Bendahara (creator) | ❌ |
| `WEEKLY_BLAST_DONE` | Bendahara trigger blast-weekly | Pendeta + Ketua Keuangan jemaat | 📤 |
| `BACKUP_COMPLETED` | Manual/auto backup selesai | Semua Admin Uni | 💾 |
| `BACKUP_FAILED` | Backup error | Semua Admin Uni | ⚠️ |
| `PENDETA_REGISTERED` | Self-register Pendeta | Semua Admin Uni | ⛪ |
| `AUDITOR_REGISTERED` | Self-register Auditor | Semua Admin Uni | 🔍 |
| `ADMIN_REGISTERED` | Self-register Admin Uni | Semua Admin Uni | 👤 |
| `TENANT_SUSPENDED` | Admin Uni suspend jemaat | Semua user di jemaat target | 🚫 |
| `TENANT_ACTIVATED` | Admin Uni activate jemaat | Semua user di jemaat target | 🟢 |

### Endpoint Baru (`/api/v1/notifications/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | List current user's notifications (paginated) |
| GET | `/notifications/unread-count` | Badge count for bell icon |
| POST | `/notifications/{id}/read` | Mark single as read |
| POST | `/notifications/read-all` | Mark all as read |
| DELETE | `/notifications/{id}` | Delete single |
| DELETE | `/notifications/clear-all` | Delete all read notifications |

**Query params:** `page`, `per_page` (1-100), `unread_only` (bool).

### Schema (`Notification`)

```python
- id (PK)
- user_id (FK → users, indexed)
- tenant_id (FK → tenants, indexed)
- event_type (String 40, indexed) — see event types above
- title (String 200)
- message (Text)
- icon (String 10, default "🔔")
- link (String 500, nullable) — deep link
- related_entity_type (String 40, nullable)
- related_entity_id (String 64, nullable)
- extra_data (JSON, nullable) — flexible payload
- is_read (Boolean, default False)
- read_at (DateTime, nullable)
- created_at (DateTime)
```

**Composite indexes:**
- `(user_id, is_read, created_at)` — bell badge query
- `(tenant_id, created_at)` — tenant-scoped history
- `(event_type, created_at)` — filter by event type

### Frontend UI

- `NotificationBell.tsx` — bell icon di Layout header dengan badge merah untuk unread count. Dropdown panel menampilkan 10 event terbaru dengan quick actions (mark read, delete). Auto-poll unread count setiap 30 detik.
- `Notifications.tsx` — dedicated `/notifications` page dengan filter (all/unread), pagination (25/50/100 per page), event-type filter, mark-all-read, dan clear-read.
- Link "🔔 Notifikasi" di sidebar untuk akses cepat.

### Cleanup & Retention

- APScheduler job `cleanup_notifications_daily` — jalan setiap hari jam 03:00 UTC
- Default retention: 90 hari (configurable via env `NOTIFICATION_RETENTION_DAYS`)
- Auto-delete notifikasi yang lebih lama dari retention
- Log: `[NOTIFICATION CLEANUP] Deleted N notifications (>X days)`

### Design Decisions

- **Self-skip:** actor yang trigger event tidak dapat notifikasi (e.g. admin yang approve tidak dapat "kuitansi disetujui" untuk dirinya sendiri)
- **Single transaction:** notification rows di-commit bersama dengan primary action (kuitansi/backup/blast), atau di-rollback bersama kalau action gagal
- **Flexible payload:** `extra_data` (JSON) menyimpan context tambahan (nomor kuitansi, total, WA target) tanpa schema migration

---

## 🌟 v2.0 — Modul Pengeluaran + PWA Quick Input + Laporan Gabungan + Managed Users

v2.0 menutup gap operasional jemaat: input dari HP, kategori fleksibel, modul Pengeluaran dengan approval, laporan gabungan PDF untuk Auditor, dan invite + void untuk manajemen user. Detail lengkap per milestone ada di [CHANGELOG.md](./CHANGELOG.md).

### Endpoint Baru (v2.0)

| Method | Path | Deskripsi |
|--------|------|-----------|
| `POST` | `/api/v1/kuitansi/quick-input` | Single-step input kuitansi dari PWA (M1) |
| `GET`  | `/api/v1/kategori/list` | Autocomplete kategori (M2) |
| `POST` | `/api/v1/pengeluaran/` | CRUD Pengeluaran (M4-M6) |
| `POST` | `/api/v1/pengeluaran/{id}/submit` | Submit draft → `pending_approval` |
| `POST` | `/api/v1/pengeluaran/{id}/approve` | Ketua Keuangan → `approved_ketua` |
| `POST` | `/api/v1/pengeluaran/{id}/reject` | Reject dengan reason |
| `GET`  | `/api/v1/laporan/gabungan?sabat_date=YYYY-MM-DD` | PDF Kuitansi + Pengeluaran per sabat (M7) |
| `POST` | `/api/v1/users/invite` | Invite user baru + kirim WA (M8) |
| `POST` | `/api/v1/kuitansi/{id}/void` | Soft-void Kuitansi (M8) |
| `POST` | `/api/v1/pengeluaran/{id}/void` | Soft-void Pengeluaran (M8) |

### Frontend Baru (v2.0)

- **`QuickInput.tsx`** — PWA single-step + dynamic multi-item + autocomplete. Offline-first via Service Worker.
- **`HalamanPengeluaran.tsx`** — List Pengeluaran + submit/approve/reject sesuai role.
- **`HalamanLaporanGabungan.tsx`** (pending frontend) — Sabat selector + PDF preview.

### Modul Pengeluaran — Status Workflow

```
draft → pending_approval (Bendahara submit)
       → approved_ketua (Ketua Keuangan)
       → approved (Auditor Misi)
       atau rejected (reason required)
```

- Hanya `draft` yang bisa di-void oleh Bendahara/creator. `approved_ketua` / `approved` butuh Auditor Misi (butuh approval khusus).

### RBAC Invite (M8)

| Caller | Bisa invite | Scope |
|--------|-------------|-------|
| BENDAHARA | BENDAHARA / KETUA_KEUANGAN / PENDETA | Tenant caller |
| AUDITOR_MISI | BENDAHARA / KETUA_KEUANGAN / PENDETA | Jemaat di misi caller |
| ADMIN_UNI | AUDITOR_MISI | Misi di uni caller |

Username generator: `{role}_{hint}` + suffix `_a/_b/...` per-tenant kalau collision. Temp password 10 char alphanumeric + `!`.

### Porsi Model B (v2.0 — T101 fixed)

```
pj = total × pct_jemaat
pu = total × pct_uni
pm = total − pj − pu
```

Constraint: `pct_jemaat + pct_uni ≤ 1.0` per tier. **KH SEMANTIK TERBALIK**: `pct_x_jemaat` = fraction to **MISI** (bukan Jemaat). `pct_x_jemaat = 0` → 100% X stays in Jemaat, **`pct_x_jemaat = 1` → 100% X ke Misi**. Migration `scripts/fix_pct_x_jemaat_t101.py` sudah apply.

### Smoke Test per Milestone

```bash
# M1 quick-input
.venv/bin/python3 scripts/smoke_m1.py
# M2 dynamic form
.venv/bin/python3 scripts/smoke_m2.py
# M7 laporan gabungan
.venv/bin/python3 scripts/smoke_m7.py
# M8 managed users + void
FLIPUS_WA_UNIQUE=99 .venv/bin/python3 scripts/smoke_m8.py
```

---

## License

UKIKT Internal — All rights reserved.

---

## 👤 Maintainer

**Jerry Mauri** — FLIPUS Lead
WhatsApp: 6285750113010

---

## 📚 Dokumentasi

Dokumentasi lengkap FLIPUS terorganisir dalam beberapa file:

| Dokumen | Isi | Untuk siapa |
|---|---|---|
| [`README.md`](README.md) | Overview, quick start, arsitektur | Semua orang (entry point) |
| [`docs/API.md`](docs/API.md) | Referensi 104 endpoint API + 39 OpenAPI tags | Frontend dev, integrasi |
| [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | Panduan pengguna (deprecated — lihat README) | Bendahara, admin jemaat |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model, PII encryption, secret rotation, incident response | Sysadmin, security reviewer |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Install, deploy, backup, monitoring, troubleshooting | Sysadmin, DevOps, on-call |
| [`docs/TESTING.md`](docs/TESTING.md) | Test suite (166 test), coverage breakdown, cara menulis test | Developer, QA |
| [`ARCHITECTURE_MAP.md`](ARCHITECTURE_MAP.md) | High-level architecture, dependency graph | Developer, arsitek |
| [`CHANGELOG.md`](CHANGELOG.md) | Riwayat perubahan per versi | Semua |
| [`FASE2_VALIDASI_AKUNTANSI.md`](FASE2_VALIDASI_AKUNTANSI.md) | Hasil audit accounting integrity per tenant | Auditor, pendeta |
| [`FASE3_AUDIT_BUG_SECURITY.md`](FASE3_AUDIT_BUG_SECURITY.md) | Bug & security findings FASE 3 | Developer, security |
| [`FASE3_SPRINT1_SUMMARY.md`](FASE3_SPRINT1_SUMMARY.md) | Ringkasan sprint 1-4 FASE 3 | Project manager, lead |
| [`storage/SECURITY_PROCEDURES.md`](storage/SECURITY_PROCEDURES.md) | Prosedur rotasi secret key detail | Sysadmin |
| [`tests/TESTS.md`](tests/TESTS.md) | Coverage matrix historis per tahap | Developer |

### Development Tools (S4-A)

```bash
make help          # lihat semua target
make test          # jalankan 166 test
make test-cov      # + coverage report
make coverage      # HTML report ke htmlcov/
make lint          # ruff linter
make lint-fix      # ruff + auto-fix
make typecheck     # mypy gradual
make clean         # hapus cache
```

