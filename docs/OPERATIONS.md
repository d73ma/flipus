# FLIPUS — Operations Guide

> **Version**: 2.0 (FASE 3 Sprint 4 — Consolidated Operations Documentation)
> **Scope**: install, deploy, backup, restore, monitoring, scheduler, troubleshooting
> **Audience**: sysadmin, DevOps, on-call
> **Lihat juga**: [`docs/SECURITY.md`](SECURITY.md:1) untuk secret/incident, [`docs/TESTING.md`](TESTING.md:1) untuk test ops

---

## 1. Arsitektur Production

```
                    ┌──────────────────┐
                    │   Cloudflare /   │  (TODO: ops S4-C+4)
                    │   Nginx (HTTPS)  │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
       ┌──────▼──────┐              ┌──────▼──────┐
       │  Frontend   │              │   Backend   │
       │  React SPA  │              │   FastAPI   │
       │  :5173 dev  │              │   :8000     │
       │  :80 prod   │              │  4 workers  │
       └─────────────┘              └──────┬──────┘
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                │                          │                          │
        ┌───────▼───────┐         ┌────────▼────────┐        ┌───────▼────────┐
        │  SQLite (dev) │         │  PostgreSQL 15  │        │  APScheduler   │
        │  flipus.db    │         │  (prod option)  │        │  (in-process)  │
        └───────────────┘         └─────────────────┘        └────────────────┘
                │
                │
        ┌───────▼──────────────────────────────────────────────────────────────┐
        │  Filesystem: storage/                                                │
        │   ├── backups/         (DB snapshots, retention 30d)                 │
        │   ├── logs/            (JSON-lines audit + app logs)                  │
        │   ├── tenants/{id}/    (logo + branding per tenant)                  │
        │   ├── scans/           (OCR uploads)                                 │
        │   ├── kuitansi/        (PDF generated)                               │
        │   └── scripts/         (operational scripts)                         │
        └──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Instalasi

### 2.1 Prasyarat

| Komponen | Versi Minimum | Catatan |
|---|---|---|
| Python | 3.11+ | 3.12 tested |
| Node.js | 18+ | untuk build frontend |
| PostgreSQL | 15+ (opsional) | default SQLite cukup untuk ≤10 user concurrent |
| RAM | 1 GB | 2 GB recommended |
| Disk | 5 GB | +1 GB per 10K kuitansi (estimasi) |

### 2.2 Quick Start (Development)

```bash
git clone <repo> flipus && cd flipus

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Env file
cp .env.example .env
# Edit .env: SECRET_KEY, PII_ENCRYPTION_KEY (lihat §2.3)

# Init DB + seed demo data (opsional)
python3 scripts/seed_demo.py

# Run
uvicorn app.main:app --reload --port 8000

# Frontend (terminal baru)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

### 2.3 Generate Secret Keys

```bash
# SECRET_KEY (JWT signing, 64 char)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# PII_ENCRYPTION_KEY (Fernet, 44 char base64)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# GEMINI_API_KEY — dapat dari https://aistudio.google.com/app/apikey
# FONNTE_TOKEN — dapat dari https://md.fonnte.com (WA gateway)
```

Simpan di `.env`:
```bash
SECRET_KEY=<hasil>
PII_ENCRYPTION_KEY=<hasil>
GEMINI_API_KEY=<dari-google>
FONNTE_TOKEN=<dari-fonnte>
```

### 2.4 Production Install (Docker)

```bash
# 1. Clone & env
cp .env.example .env && nano .env

# 2. HTTPS cert (Let's Encrypt)
./storage/scripts/setup_https.sh your-domain.com admin@your-domain.com

# 3. Up
docker compose up -d

# 4. Verify
docker compose ps
docker compose logs -f backend
curl https://your-domain.com/api/v1/health
```

Lihat [`docker-compose.yml`](../../docker-compose.yml) untuk service definition.

---

## 3. Deployment

### 3.1 Environment Variables

Lihat `.env.example` untuk daftar lengkap. **WAJIB** diset sebelum production:

| Var | Wajib | Contoh | Keterangan |
|---|---|---|---|
| `SECRET_KEY` | ✅ | `AbC...xyz=` | JWT signing |
| `PII_ENCRYPTION_KEY` | ✅ | `AbC...xyz=` | Fernet PII |
| `DATABASE_URL` | opsional | `postgresql://user:pwd@host/db` | default SQLite |
| `CORS_ORIGINS` | ✅ | `https://app.example.com` | comma-separated |
| `DEMO_MODE` | ✅ | `false` | `true` hanya untuk demo |
| `LOG_LEVEL` | ✅ | `INFO` | DEBUG untuk troubleshooting |
| `GEMINI_API_KEY` | untuk OCR | `AIza...` | |
| `FONNTE_TOKEN` | untuk WA bot | `abc123` | |
| `BACKUP_GPG_RECIPIENT` | opsional | `backup@example.com` | untuk encrypted backup |

### 3.2 HTTPS Setup

```bash
./storage/scripts/setup_https.sh flipus.example.com admin@flipus.example.com
```

Cert auto-renew via certbot. Lihat [`storage/scripts/setup_https.sh`](../../storage/scripts/setup_https.sh).

### 3.3 Database Migration (SQLite → PostgreSQL)

```bash
# 1. Backup SQLite
cp flipus.db flipus-pre-migration.db

# 2. Export
.venv/bin/python3 scripts/migrate_sqlite_to_postgres.py export > dump.sql

# 3. Set DATABASE_URL di .env
echo 'DATABASE_URL=postgresql://flipus:STRONG@postgres:5432/flipus' >> .env

# 4. Import
.venv/bin/python3 scripts/migrate_sqlite_to_postgres.py import dump.sql

# 5. Verify row count
.venv/bin/python3 -c "
from app.core.database import SessionLocal
from app.models.transaction import Kuitansi
db = SessionLocal()
print(f'Kuitansi: {db.query(Kuitansi).count()}')
"
```

### 3.4 Frontend Build

```bash
cd frontend
npm run build
# Output: frontend/dist/  → served by Nginx di production
```

Set `VITE_API_BASE_URL` di `.env.production` ke `https://your-domain.com/api`.

---

## 4. Backup & Restore

### 4.1 Jadwal Backup (APScheduler)

| Job | Waktu (UTC) | Apa |
|---|---|---|
| `Auto-backup DB` | 02:00 harian | copy `flipus.db` → `storage/backups/flipus-YYYY-MM-DD_HHMMSS.db` |
| `Auto-reset on first Saturday of January` | Sat 00:00 (1st week Jan) | reset porsi tahunan |
| `Notification cleanup` | 03:00 harian | hapus notifikasi > 90 hari |

Log scheduler:
```
[SCHEDULER] Started — backup 02:00, reset Sat 08:00, notif cleanup 03:00 UTC
```

### 4.2 Backup Manual

```bash
# Standalone (SQLite)
cp flipus.db storage/backups/flipus-manual-$(date +%Y%m%d_%H%M%S).db

# Dengan GPG encryption
./storage/scripts/backup_gpg.sh

# PostgreSQL
pg_dump -U flipus -h postgres flipus > storage/backups/flipus-$(date +%Y%m%d).sql
```

### 4.3 Restore

**Via API (admin only)**:
```bash
curl -X POST https://your-domain.com/api/v1/admin/restore-db \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filename": "flipus-2026-09-02_020000.db"}'
```

**Via CLI**:
```bash
# 1. Stop backend
docker compose stop backend

# 2. Replace DB
cp storage/backups/flipus-2026-09-02_020000.db flipus.db

# 3. Start
docker compose start backend

# 4. Verify
curl https://your-domain.com/api/v1/health
```

### 4.4 Retention

Default: 30 hari di `storage/backups/`. Cleanup otomatis harian oleh APScheduler.

Manual cleanup:
```bash
find storage/backups/ -name "flipus-*.db" -mtime +30 -delete
```

---

## 5. Monitoring & Logging

### 5.1 Health Check

```bash
curl https://your-domain.com/api/v1/health
# {"status":"ok","db":"ok","version":"2.0.0"}
```

Gunakan untuk uptime monitoring (UptimeRobot, Pingdom, dll).

### 5.2 Logs

**Lokasi**:
- Stdout (Docker): `docker compose logs -f backend`
- File (opsional): `storage/logs/app-YYYY-MM-DD.jsonl`

**Format**: JSON-lines, satu event per baris:
```json
{"ts":"2026-09-02T23:00:00Z","level":"INFO","logger":"app.api","msg":"kuitansi_created","user_id":"u_123","tenant_id":"t_1","kuitansi_id":"k_456","request_id":"r_abc"}
```

**Query berguna**:
```bash
# Error 500 dalam 24 jam terakhir
docker compose logs backend --since 24h | grep -E '"level":"ERROR"' | jq .

# Login gagal
docker compose logs backend --since 24h | grep '"login_failed"' | jq -r '.ip' | sort | uniq -c

# Rate limit hit
docker compose logs backend --since 1h | grep -E '"RATE_LIMITED"|"429"'
```

### 5.3 Metrics (TODO)

**TODO S4-C+5**: Prometheus exporter di `/metrics`. Saat ini health check saja.

---

## 6. Scheduled Jobs (APScheduler)

### 6.1 Definisi Job

| Job ID | Trigger | Fungsi | File |
|---|---|---|---|
| `auto_backup_db` | cron `0 2 * * *` | backup harian | [`app/services/backup_service.py`](../../app/services/backup_service.py) |
| `auto_reset_porsi` | cron `0 0 1-7 1 SAT` | reset porsi tahunan | [`app/services/reset_service.py`](../../app/services/reset_service.py) |
| `cleanup_notifications` | cron `0 3 * * *` | cleanup notif > 90 hari | [`app/services/notification_cleanup.py`](../../app/services/notification_cleanup.py) |

### 6.2 Inspect Scheduler

```bash
.venv/bin/python3 -c "
from app.main import app
# Scheduler ada di app.state.scheduler
sch = app.state.scheduler
for job in sch.get_jobs():
    print(f'{job.id}: next_run={job.next_run_time}')
"
```

### 6.3 Trigger Manual (untuk testing)

```bash
# Via API admin
curl -X POST https://your-domain.com/api/v1/admin/trigger-backup \
  -H "Authorization: Bearer $ADMIN_TOKEN"

curl -X POST https://your-domain.com/api/v1/admin/trigger-reset \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 7. Troubleshooting

### 7.1 Backend tidak start

**Symptom**: `docker compose up` exit dengan error

**Cek**:
```bash
docker compose logs backend
```

**Common causes**:
- `.env` tidak ada atau `SECRET_KEY` kosong → `cp .env.example .env` lalu edit
- DB file permission denied → `chown 1000:1000 flipus.db`
- Port 8000 sudah dipakai → ubah di `docker-compose.yml`

### 7.2 Login gagal terus

**Cek**:
```bash
# User exists?
.venv/bin/python3 -c "
from app.core.database import SessionLocal
from app.models.user import User
db = SessionLocal()
u = db.query(User).filter(User.email=='admin@example.com').first()
print(f'Found: {u}, is_active: {u.is_active if u else None}')
"
```

**Fix**:
```bash
# Reset password
.venv/bin/python3 scripts/rehash_passwords.py

# Atau activate user
.venv/bin/python3 -c "
from app.core.database import SessionLocal
from app.models.user import User
db = SessionLocal()
u = db.query(User).filter(User.email=='admin@example.com').first()
u.is_active = True
db.commit()
"
```

### 7.3 Scheduler tidak jalan

**Symptom**: backup tidak terbuat, notifikasi tidak cleanup

**Cek log**:
```bash
docker compose logs backend | grep -i scheduler
```

**Fix**:
- Pastikan APScheduler started (lihat log startup)
- Cek timezone: APScheduler pakai UTC; `0 2 * * *` = 02:00 UTC = 10:00 WITA

### 7.4 WA bot tidak terima pesan

**Cek**:
```bash
# Fonnte device status
curl -H "Authorization: $FONNTE_TOKEN" https://api.fonnte.com/device
```

**Common causes**:
- `FONNTE_TOKEN` expired → regenerate di dashboard Fonnte
- Device Fonnte belum scan QR
- Webhook URL tidak bisa diakses dari Fonnte (perlu public HTTPS)

### 7.5 OCR gagal

**Cek**:
- `GEMINI_API_KEY` valid?
- Quota API belum habis?

```bash
.venv/bin/python3 -c "
import google.generativeai as genai
genai.configure(api_key='YOUR_KEY')
model = genai.GenerativeModel('gemini-1.5-flash')
print(model.generate_content('test').text)
"
```

### 7.6 Storage penuh

**Cek**:
```bash
du -sh storage/* | sort -h
```

**Cleanup**:
```bash
# Backup lama (> 30 hari)
find storage/backups/ -name "*.db" -mtime +30 -delete

# Log lama (> 90 hari)
find storage/logs/ -name "*.jsonl" -mtime +90 -delete

# Scan orphan
.venv/bin/python3 scripts/retention_daemon.py
```

### 7.7 Performance lambat

**Symptom**: API response > 2 detik

**Cek**:
- Index DB ada? (lihat [`app/models/`](../../app/models/) — composite index di T22)
- Connection pool cukup?
- N+1 query? (lihat FASE 2 audit)

**Fix sementara**: scale workers:
```bash
# docker-compose.yml
backend:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 8
```

---

## 8. Maintenance Routine

### 8.1 Harian (otomatis)

- ✅ Backup DB 02:00 UTC
- ✅ Cleanup notifikasi 03:00 UTC
- ✅ Secret rotation check (opsional, via script)

### 8.2 Mingguan (manual, ~15 menit)

```bash
# Cek log error
docker compose logs backend --since 7d | grep '"level":"ERROR"' | wc -l

# Cek disk usage
df -h /var/lib/docker

# Cek backup integrity (ambil 1 file terakhir, test restore ke staging)
cp storage/backups/flipus-latest.db /tmp/test-restore.db
sqlite3 /tmp/test-restore.db "PRAGMA integrity_check;"
```

### 8.3 Bulanan (manual, ~30 menit)

```bash
# Rotate SECRET_KEY (jadwal 6 bulan, tapi cek setiap bulan)
./storage/scripts/rotate_secret_key.sh --no-restart

# Review audit log untuk anomali
docker compose logs backend --since 30d | grep -E '"login_failed"|"RATE_LIMITED"' | jq -r '.ip' | sort | uniq -c | sort -rn | head

# Update dependencies
pip list --outdated
```

### 8.4 Tahunan (manual, ~2 jam)

- Rotate `PII_ENCRYPTION_KEY` (lihat [`docs/SECURITY.md` §3.3](SECURITY.md:33))
- Penetration test (TODO — belum dijadwalkan)
- Review & update dokumentasi
- Capacity planning review

---

## 9. Disaster Recovery

### 9.1 Skenario: Single Server Crash

1. Spin up server baru (same image)
2. Mount backup volume
3. Restore DB terakhir: `cp storage/backups/flipus-latest.db flipus.db`
4. `docker compose up -d`
5. Verify health check
**RTO**: ~30 menit · **RPO**: max 24 jam

### 9.2 Skenario: Data Center Total Loss

**TODO S4-C+3**: off-site backup belum di-setup. Saat ini semua di single server.

Mitigasi sementara: rsync harian `storage/backups/` ke server kedua via cron:
```bash
0 4 * * * rsync -avz /app/storage/backups/ backup@server2:/backups/flipus/
```

### 9.3 Skenario: Database Corruption

1. Stop backend
2. `sqlite3 flipus.db "PRAGMA integrity_check;"` → jika corrupt:
3. Restore dari backup terakhir
4. Investigate root cause (disk failure? mid-write crash?)

---

## 10. Referensi

- [`docs/SECURITY.md`](SECURITY.md:1) — secret management, incident response
- [`docs/TESTING.md`](TESTING.md:1) — cara run test, CI integration
- [`storage/SECURITY_PROCEDURES.md`](../SECURITY_PROCEDURES.md) — rotate key detail
- [`storage/scripts/`](../../storage/scripts/) — operational scripts (backup_gpg, rotate_secret_key, setup_https, dll)
- [`scripts/`](../../scripts/) — migration & utility scripts
- [`ARCHITECTURE_MAP.md`](../../ARCHITECTURE_MAP.md) — high-level architecture
- [`docker-compose.yml`](../../docker-compose.yml) — service definition
