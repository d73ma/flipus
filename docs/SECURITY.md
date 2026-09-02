# FLIPUS — Security Guide

> **Version**: 2.0 (FASE 3 Sprint 4 — Consolidated Security Documentation)
> **Scope**: threat model, secret management, PII encryption, auth/2FA, rate limiting, audit, incident response
> **Audience**: sysadmin, DevOps, security reviewer
> **Lihat juga**: [`storage/SECURITY_PROCEDURES.md`](../storage/SECURITY_PROCEDURES.md) untuk prosedur rotasi secret key

---

## 1. Threat Model

### 1.1 Aset yang Dilindungi

| Aset | Lokasi | Klasifikasi |
|---|---|---|
| Data kuitansi/pengeluaran jemaat | SQLite/PostgreSQL DB | **Confidential** (PII) |
| Password user | DB (bcrypt hash) | **Confidential** |
| PII tambahan (NIK, no HP, nama asli) | DB (Fernet encrypted) | **Sensitive PII** |
| JWT access/refresh token | client-side (memory + httpOnly cookie) | **Critical** |
| `SECRET_KEY` (JWT signing) | `.env` | **Critical** |
| `PII_ENCRYPTION_KEY` (Fernet) | `.env` | **Critical** |
| `GEMINI_API_KEY` (OCR) | `.env` | **Secret** |
| `FONNTE_TOKEN` (WA gateway) | `.env` | **Secret** |
| Logo/branding tenant | `storage/tenants/{id}/` | **Public** (per tenant) |
| Backup DB | `storage/backups/` | **Confidential** |

### 1.2 Ancaman yang Dipertimbangkan

| # | Ancaman | Mitigasi |
|---|---|---|
| T1 | **Password brute force** | bcrypt (cost 12) + rate limit login 5 req/menit/IP |
| T2 | **JWT token theft** | short-lived access (15 min) + refresh rotation + httpOnly + Secure cookie |
| T3 | **Account takeover** | 2FA/TOTP opsional (Tahap 23) + backup codes |
| T4 | **SQL injection** | SQLAlchemy ORM parameterized queries |
| T5 | **Cross-tenant data leak** | JWT claim `tid` + WHERE `tenant_id=:tid` di setiap query (lihat FASE 2 audit) |
| T6 | **PII breach via DB dump** | Fernet encryption untuk kolom sensitif |
| T7 | **File upload exploit** | filetype magic byte validation + size limit + storage di luar webroot |
| T8 | **API abuse / scraping** | slowapi rate limit (60 req/menit/IP global) |
| T9 | **XSS di kuitansi PDF** | reportlab escaping + sanitasi input nama |
| T10 | **CSRF** | JWT di header `Authorization` (bukan cookie otomatis) + SameSite=Lax |
| T11 | **Secret leak via git** | `.env` di-`.gitignore` + secret scanner di CI |
| T12 | **Backup theft** | GPG encryption (opsional via `backup_gpg.sh`) |
| T13 | **Privilege escalation** | RBAC role enum (`admin`, `pendeta`, `auditor`, `bendahara`, `majelis`) + decorator `@require_role` |
| T14 | **Replay attack (WA bot)** | per-user state machine + idempotency key |
| T15 | **Logout incomplete** | refresh token rotation + blacklist saat logout |

---

## 2. Autentikasi & Otorisasi

### 2.1 Password Policy

- Min 8 char (frontend validation, backend tidak re-validate → **TODO S4-C+1**: tambah backend min length)
- bcrypt cost factor = 12 (lihat [`app/core/security.py`](app/core/security.py))
- Salt otomatis per user (bcrypt built-in)
- Rehash otomatis jika cost berubah saat login

**Cara rotate password semua user (misal setelah breach)**:
```bash
.venv/bin/python3 scripts/rehash_passwords.py
```

### 2.2 JWT Token

- **Algoritma**: HS256 (python-jose)
- **Access token**: 15 menit (`ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Refresh token**: 7 hari (`REFRESH_TOKEN_EXPIRE_DAYS`)
- **Claims**: `sub` (user_id), `tid` (tenant_id), `role`, `exp`, `iat`
- **Refresh rotation**: setiap `POST /auth/refresh` issued refresh token baru + invalidate yang lama

**Key rotation**: lihat [`storage/SECURITY_PROCEDURES.md`](../storage/SECURITY_PROCEDURES.md) §1 — pakai `rotate_secret_key.sh` (24 jam grace window via `SECRET_KEY_PREVIOUS`).

### 2.3 Two-Factor Authentication (TOTP)

- Standar: RFC 6238 (TOTP-SHA1, 30 detik, 6 digit)
- Library: `pyotp` + `qrcode[pil]`
- Backup codes: 10 kode hex 8 char (one-time use, hashed di DB)
- Endpoint: lihat [`docs/API.md` §4.2](API.md:42)
- **Mandatory untuk role admin** (Tahap 23) — soft enforced, frontend wajib prompt

### 2.4 Role-Based Access Control

| Role | Scope | Permission |
|---|---|---|
| `admin` | tenant | semua kecuali Jerry-only endpoint |
| `pendeta` | tenant | approve kuitansi/pengeluaran, view reports |
| `auditor` | tenant + cross-tenant (read) | view-only semua data + laporan gabungan |
| `bendahara` | tenant | CRUD kuitansi/pengeluaran |
| `majelis` | tenant | view-only reports |
| `superadmin` | cross-tenant | Jerry-only (`/api/v1/admin/*`) |

Decorator enforcement: `@require_role("admin", "pendeta")` di [`app/core/security.py`](app/core/security.py).

---

## 3. PII Encryption

### 3.1 Skema

- Algoritma: **Fernet** (AES-128-CBC + HMAC-SHA256) dari `cryptography`
- Key: `PII_ENCRYPTION_KEY` di `.env` (44 char base64)
- Enkripsi field-level, bukan row-level (lebih fleksibel untuk query)

### 3.2 Field yang Dienkripsi

Lihat [`app/models/user.py`](app/models/user.py) dan tabel anomali di [`storage/SECURITY_PROCEDURES.md`](../storage/SECURITY_PROCEDURES.md):

- `User.nama_lengkap`
- `User.no_hp`
- `User.nik` (jika ada)
- `Kuitansi.nama_penyetor` (jika ada PII pihak ketiga)
- `Pengeluaran.nama_penerima` (jika transfer ke pribadi)

### 3.3 Key Rotation

```bash
# 1. Generate key baru
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Set di .env: PII_ENCRYPTION_KEY=<new>, PII_ENCRYPTION_KEY_PREVIOUS=<old>

# 3. Re-encrypt
.venv/bin/python3 scripts/rotate_pii_to_new_key.py

# 4. Setelah 24 jam, hapus PII_ENCRYPTION_KEY_PREVIOUS
```

Lihat [`scripts/rotate_pii_to_new_key.py`](../../scripts/rotate_pii_to_new_key.py).

---

## 4. Upload Security

### 4.1 Validasi Berlapis

Lihat [`app/core/upload_validator.py`](app/core/upload_validator.py):

1. **Ekstensi allowlist**: `.jpg`, `.jpeg`, `.png`, `.pdf`
2. **Magic byte check**: pakai `filetype` library (bukan hanya MIME header)
3. **Size limit**: 10 MB per file
4. **Storage path**: di luar webroot (`storage/scans/`, `storage/tenants/{id}/logo/`)
5. **Filename**: UUID-based (no original filename preserved)

### 4.2 Anti-Malware

**TODO S4-C+2**: integrasi ClamAV untuk production. Saat ini hanya magic byte + size check.

---

## 5. Rate Limiting

Lihat [`app/core/rate_limiter.py`](app/core/rate_limiter.py) — slowapi-based:

| Scope | Limit | Identifier |
|---|---|---|
| Global | 60 req/menit | IP |
| `/auth/login` | 5 req/menit | IP |
| `/auth/2fa/*` | 10 req/menit | user_id |
| Upload (OCR/scan) | 20 req/jam | IP |
| WA bot inbound | 30 req/menit | phone_number |

Response 429:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests",
    "retry_after": 42
  }
}
```

---

## 6. Audit Logging

### 6.1 Yang Di-Log

Lihat [`app/core/logging.py`](app/core/logging.py):

- **Auth events**: login (success/fail), logout, 2FA setup/verify, password change, refresh
- **Data mutation**: create/update/delete kuitansi, pengeluaran, user, tenant
- **Admin actions**: backup, restore, manual reset, recompute porsi
- **Security events**: rate limit hit, invalid JWT, SQL injection attempt, file upload rejection

### 6.2 Format

JSON-lines, satu event per baris:
```json
{"ts":"2026-09-02T23:00:00Z","level":"INFO","logger":"app.auth","msg":"login_success","user_id":"u_123","tenant_id":"t_1","ip":"10.0.0.5","request_id":"r_abc"}
```

### 6.3 Lokasi

- **Stdout** (untuk Docker log driver)
- **File** (opsional): `storage/logs/app-YYYY-MM-DD.jsonl`

---

## 7. Backup & Restore Security

### 7.1 Backup

- **Jadwal**: harian 02:00 UTC (APScheduler)
- **Lokasi default**: `storage/backups/flipus-YYYY-MM-DD_HHMMSS.db`
- **Retention**: 30 hari (lokal), cleanup otomatis
- **GPG encryption** (opsional): `storage/scripts/backup_gpg.sh`

### 7.2 Restore

```bash
# Via API (admin only)
POST /api/v1/admin/restore-db  body={"filename": "flipus-2026-09-02_020000.db"}

# Via CLI
cp storage/backups/flipus-2026-09-02_020000.db flipus.db
# Restart backend
```

**PERINGATAN**: restore akan overwrite DB aktif. Pastikan tenant tahu via notifikasi dulu.

### 7.3 Disaster Recovery

| Skenario | RPO | RTO |
|---|---|---|
| Single server crash | 24 jam (daily backup) | 30 menit |
| DB corruption | 24 jam | 30 menit |
| Server compromised (DB encrypted) | 0 (Fernet-protected PII) | 1 jam (re-image + restore) |
| Total data center loss | Tergantung off-site backup policy | Tergantung |

**TODO S4-C+3**: setup off-site backup (S3 B2 atau rsync ke server kedua). Belum diimplementasi.

---

## 8. Insiden Response

### 8.1 Severity Levels

| Level | Contoh | Response time |
|---|---|---|
| **P0** | DB breach, secret leak ke public repo | < 1 jam |
| **P1** | Single user account takeover, auth bypass | < 4 jam |
| **P2** | Rate limit bypass, info disclosure minor | < 24 jam |
| **P3** | UX security issue, missing header | < 1 minggu |

### 8.2 Prosedur P0

1. **Isolate**: revoke `SECRET_KEY` (rotate), disable affected endpoint
2. **Assess**: cek audit log untuk scope breach
3. **Notify**: lapor ke Jerry + tim UKIKT + jemaat jika PII exposed
4. **Remediate**: patch + deploy hotfix
5. **Post-mortem**: tulis di [`FASE3_AUDIT_BUG_SECURITY.md`](../FASE3_AUDIT_BUG_SECURITY.md) dalam 48 jam

### 8.3 Secret Leak Response

Jika `.env` ter-commit ke git (哪怕 dihapus kemudian):

```bash
# 1. Rotate SEMUA secret SEGERA
./storage/scripts/rotate_secret_key.sh
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # PII key
# Regenerate GEMINI_API_KEY, FONNTE_TOKEN

# 2. Cek history git
git log --all --full-history -- .env
# Jika ada commit, anggap compromised → rotate semua token dependent

# 3. Purge dari history (gunakan BFG Repo Cleaner)
bfg-repo-cleaner --delete-files .env
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

---

## 9. Compliance Checklist

| Item | Status | Bukti |
|---|---|---|
| PII encryption at rest | ✅ | Fernet untuk field sensitif |
| PII encryption in transit | ✅ | HTTPS (Let's Encrypt) di production |
| Password hashing (bcrypt/argon2) | ✅ | bcrypt cost 12 |
| Audit log untuk data mutation | ✅ | JSON-lines ke stdout + file |
| Rate limiting | ✅ | slowapi |
| File upload validation | ✅ | filetype + size + path |
| Multi-tenant isolation | ✅ | FASE 2 audit (`FASE2_VALIDASI_AKUNTANSI.md`) |
| 2FA untuk admin | ✅ (soft) | Tahap 23, frontend wajib |
| Secret rotation | ✅ | scripts tersedia |
| Backup encryption (off-site) | ⚠️ Partial | GPG opsional, off-site TODO |
| WAF / DDoS protection | ❌ | TODO production |
| Penetration test terakhir | ❌ | TODO post-FASE 4 |
| GDPR/UU PDP compliance review | ❌ | TODO (konsultasi hukum) |

---

## 10. Referensi

- [`storage/SECURITY_PROCEDURES.md`](../storage/SECURITY_PROCEDURES.md) — prosedur operasional (rotate secret, backup GPG, dll)
- [`FASE3_AUDIT_BUG_SECURITY.md`](../FASE3_AUDIT_BUG_SECURITY.md) — audit bug & security findings FASE 3
- [`docs/API.md` §4](API.md:42) — auth flow detail
- [`docs/OPERATIONS.md`](OPERATIONS.md:1) — install/deploy/maintenance
- OWASP Top 10 (2021): https://owasp.org/www-project-top-ten/
- python-jose: https://python-jose.readthedocs.io/
- cryptography (Fernet): https://cryptography.io/en/latest/fernet/
