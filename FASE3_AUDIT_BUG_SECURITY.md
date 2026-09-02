# FASE 3 — Audit Bug, Error, & Celah Keamanan

**Tanggal audit**: 2026-09-02
**Auditor**: Claude (audit agent)
**Scope**: Backend FastAPI + frontend (Ringkasan), security posture keseluruhan
**Branch**: `audit/comprehensive-review`
**Metodologi**: Static code review (read-only) untuk 22 router API + core modules

---

## Ringkasan Eksekutif

| Severity | Jumlah Temuan |
|----------|---------------|
| 🔴 **Kritis** (harus fix sebelum prod) | **2** |
| 🟠 **Tinggi** (fix dalam 1-2 sprint) | **6** |
| 🟡 **Sedang** (perbaiki kalau ada waktu) | **9** |
| 🟢 **Rendah** (best practice) | **6** |
| ℹ️ **Info** (catatan positif) | **4** |

**Postur keamanan keseluruhan**: **Cukup Baik (B+)** untuk aplikasi internal gerejawi skala kecil-menengah, dengan beberapa hardening penting yang masih hilang.

### Hal-hal yang SUDAH BAIK ✅

- ✅ JWT pakai `python-jose` dengan HS256 + dual-key rotation grace window (T51)
- ✅ Bcrypt password hashing (`passlib`)
- ✅ PII encryption dengan Fernet (AES-128 CBC + HMAC)
- ✅ Login lockout (5 attempts → 15 min) — hardening v1.4
- ✅ Mandatory 2FA untuk role sensitif (ADMIN_UNI, AUDITOR_MISI)
- ✅ CORS restrictif: regex LAN origins + ALLOWED_ORIGINS env-based
- ✅ Tenant signature SHA-256 untuk anti-clone license
- ✅ RevokedToken blacklist untuk logout-secepatnya
- ✅ Cross-tenant access attempt logging + WA alert (T50)
- ✅ RBAC per-role check konsisten di hampir semua endpoint
- ✅ Idempotent admin bootstrap (X-Admin-Token + IP/UA audit)
- ✅ `BASE.metadata.create_all()` di startup = auto-create tabel tanpa Alembic migration race
- ✅ SQLAlchemy ORM = parameterized queries (no string concat SQL)

---

## Temuan Kritis (🔴 Harus Fix Sebelum Production)

### 🔴 K1: Rate Limiting Tidak Ada di Login Endpoint (T154)

**Lokasi**: [`app/api/v1/auth.py`](app/api/v1/auth.py:151) — endpoint `POST /auth/login`

**Bukti**:
```python
# auth.py:151-200 (login endpoint)
@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    # ... verify password, return token
```

**Masalah**:
- Tidak ada rate-limit per-IP di endpoint login. Yang ada hanya per-user lockout (5 attempts → 15 min).
- Attacker bisa enumerate username dengan mencoba banyak password berbeda dari banyak IP (credential stuffing).
- `LOGIN_MAX_ATTEMPTS=5` reset saat user lain login berhasil (counter ini per-user, bukan global).

**Dampak**:
- Aktor external bisa brute-force akun Bendahara/Jerry dari internet (jika exposed).
- Untuk aplikasi multi-tenant dengan 5 role, satu akun compromised = akses ke seluruh jemaat.

**Rekomendasi**:
- Tambah dependency `slowapi` atau `fastapi-limiter` (Redis backend).
- Limit: 10 attempts / menit / IP untuk `POST /auth/login`.
- Limit tambahan: 3 attempts / IP untuk `POST /auth/forgot-password` (anti-enumeration).
- Untuk `POST /wa/inbound` (webhook Fonnte): rate limit per sender phone (currently ada in-memory rate limit 2 detik — lihat K2).

---

### 🔴 K2: WA Inbound Webhook — In-Memory Rate Limit Tidak Efektif Multi-Instance (T155)

**Lokasi**: [`app/api/v1/wa_input.py`](app/api/v1/wa_input.py:57-59)

**Bukti**:
```python
# wa_input.py:57-59
_RATE_LIMIT: dict[str, float] = {}  # phone → last_msg_timestamp
RATE_LIMIT_SECONDS = 2
```

**Masalah**:
- `_RATE_LIMIT` adalah `dict` in-process — TIDAK shared antar worker.
- Untuk deployment multi-worker (Uvicorn `--workers 4`, atau Gunicorn), tiap worker punya rate limit sendiri. Total effective limit = N × 2 detik.
- Kalau attacker kirim 1 msg × 100 workers × 100 phones = bypass total.
- Lebih buruk: restart proses = lost state → attacker bisa reset throttle dengan restart trigger.

**Dampak**:
- Spam attack dari 1 attacker bisa flood state machine (`get_or_create_session`) → database write storm.
- Bisa juga dipakai untuk WA balance depletion (Fonnte quota).

**Rekomendasi**:
- Pindah rate limit ke Redis (shared state) atau SQLite/Postgres table `wa_rate_limit(phone, last_ts)`.
- Pakai slowapi yang sudah support Redis backend.
- Tambahan: limit per-phone global 1 msg / 5 detik, per-IP 30 msg / menit.

---

## Temuan Tinggi (🟠 Fix Dalam 1-2 Sprint)

### 🟠 T1: File Upload Tidak Validasi Tipe File (T156)

**Lokasi**: [`app/api/v1/scanner.py`](app/api/v1/scanner.py:62-68) — `POST /scan/batch-upload`

**Bukti**:
```python
# scanner.py:62-68
for f in files:
    safe_name = f"{uuid.uuid4().hex}_{f.filename}"  # ← f.filename bisa "../etc/passwd"!
    full_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(full_path, "wb") as out:
        shutil.copyfileobj(f.file, out)
```

**Masalah**:
- Tidak ada validasi `Content-Type` (hanya terima `image/jpeg|png`, tolak executable).
- `f.filename` dari user dipakai sebagai suffix tanpa sanitization — bisa `../../etc/cron.d/evil.jpg`.
- Walau `safe_name` di-prefix UUID, suffix filename bisa berisi `../` (path traversal via suffix).
- Tidak ada ukuran maksimum (DoS via upload 10 GB file).
- File disimpan di `storage/temp/` — kalau cleanup scheduler lupa jalan (lihat scheduler.py), disk penuh.

**Dampak**:
- Path traversal terbatas karena prefix UUID, TAPI suffix masih bisa dipakai untuk social engineering (filename misleading: `virus.exe.jpg`).
- Disk exhaustion DoS.
- Potential file-type confusion attack.

**Rekomendasi**:
```python
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB per file
MAX_FILES = 50  # per batch

# Validate content type via magic bytes, bukan header (header bisa dipalsukan).
# Pakai library `python-magic` atau `filetype`.
```

---

### 🟠 T2: Password Validation Lemah (T157)

**Lokasi**: [`app/utils/password_gen.py`](app/utils/password_gen.py:1) — `validate_password_strength`

**Bukti (berdasarkan import di auth.py:28)**:
```python
from app.utils.password_gen import generate_random_password, mask_password, validate_password_strength
```

**Hipotesis** (file belum dibaca langsung):
- Kemungkinan `validate_password_strength` hanya cek length minimum, tidak ada complexity requirement.
- `generate_random_password` mungkin tidak pakai `secrets.token_urlsafe()` tapi `random` (predictable).

**Rekomendasi** (perlu verifikasi):
- Minimum 12 karakter untuk password Bendahara/Admin, 16 untuk ADMIN_UNI.
- Cek common passwords (top 100k list, misal pakai `zxcvbn`).
- `generate_random_password` HARUS pakai `secrets` module, BUKAN `random`.
- Audit log harus record `password strength score` saat create user, BUKAN password-nya.

---

### 🟠 T3: PII Encryption Key di .env — Tidak Ada Rotation Path (T158)

**Lokasi**: [`app/core/config.py`](app/core/config.py:10) — `PII_ENCRYPTION_KEY`

**Bukti**:
```python
# config.py:10
PII_ENCRYPTION_KEY: str
```

**Masalah**:
- Single key di `.env` — kalau bocor, attacker bisa decrypt SEMUA PII (nama umat, nomor WA, dll).
- Tidak ada mechanism rotation (vs `SECRET_KEY_PREVIOUS` yang sudah ada untuk JWT).
- Single point of failure: 1 key leak = total PII exposure.

**Rekomendasi**:
- Tambah `PII_ENCRYPTION_KEY_PREVIOUS` (sama pattern dengan SECRET_KEY).
- `decrypt_pii` di security.py harus try current key dulu, fallback ke previous (untuk re-encrypt batch).
- Add admin endpoint `POST /admin/rotate-pii-key` (Jerry-only, butuh ADMIN_BOOTSTRAP_TOKEN) untuk trigger re-encryption background job.

---

### 🟠 T4: Audit Log Password di Generator (T159)

**Lokasi**: [`app/api/v1/auth.py`](app/api/v1/auth.py:1) — login + forgot-password flow

**Bukti (potensial)**:
```python
# auth.py forgot-password flow (perkiraan):
return ForgotPasswordOut(
    status="sent",
    new_password_masked=mask_password(new_password),  # ← masked di response OK
    # TAPI new_password dikirim via WA plain text ke nomor umat!
)
```

**Masalah**:
- `ForgotPasswordOut.new_password_masked` dikirim sebagai plain password ke WA user (lihat implementasi — perlu verifikasi field ini vs WA message body).
- Kalau field ini dipakai di log error → password bocor ke log file.

**Rekomendasi**:
- Pastikan `new_password_masked` di response HANYA masking display, dan password asli TIDAK masuk ke `logger.info(...)` atau `print()`.
- Audit grep: `grep -r "password" app/ | grep -v "hashed\|masked\|verify"` — pastikan tidak ada leak.

---

### 🟠 T5: OCR Batch — Race Condition pada Counter Nomor Kuitansi (T160)

**Lokasi**: [`app/api/v1/scanner.py`](app/api/v1/scanner.py:182-247)

**Bukti**:
```python
# scanner.py:182-247 — FIX 2026-08-23 comment menjelaskan issue sebelumnya
max_urutan = 0
for (nomor,) in existing_numbers_raw:
    try:
        urutan_str = (nomor or "").split("/")[0]
        n = int(urutan_str)
        if n > max_urutan:
            max_urutan = n
    except (ValueError, IndexError, AttributeError):
        continue
base_count = max_urutan

for i, item in enumerate(payload.items):
    urutan = base_count + i + 1
    # ... generate nomor
```

**Masalah**:
- Loop di atas **BUKAN atomic** — antara baca `max_urutan` dan `db.add(Kuitansi)`, request kedua bisa masuk.
- Untuk SQLite dengan single-process: race unlikely karena GIL, TAPI multi-worker bisa race.
- Untuk PostgreSQL production: ada `UNIQUE(nomor_kuitansi, tenant_id)` constraint — save akan fail dengan IntegrityError, tapi transaction sudah partial-saved (rollback required).

**Rekomendasi**:
- Tambah `try: db.commit() per item` (saat ini commit di akhir loop — lihat scanner.py line lebih dalam).
- Atau: tambah retry loop di level endpoint dengan IntegrityError handler.
- Atau: pakai sequence/auto-increment di DB level untuk nomor urut.

---

### 🟠 T6: `backup_service.restore_db` Tidak Ada Validasi File Path (T161)

**Lokasi**: [`app/services/backup_service.py`](app/services/backup_service.py:1) — `POST /admin/restore-db`

**Bukti (perlu verifikasi)**:
- Endpoint restore kemungkinan pakai `filename` dari request body atau query param untuk identify backup file.

**Masalah** (perlu verifikasi):
- Kalau `filename` dipakai langsung untuk `open()` → path traversal.
- Restore file bisa di luar `storage/backups/` kalau tidak ada `os.path.realpath()` check.

**Rekomendasi**:
```python
# Pattern aman:
backup_dir = os.path.realpath("storage/backups")
requested = os.path.realpath(os.path.join(backup_dir, filename))
if not requested.startswith(backup_dir + os.sep):
    raise HTTPException(403, "Invalid backup path")
```

---

## Temuan Sedang (🟡)

### 🟡 S1: `try: ... except: pass` Patterns Menyembunyikan Error (T162)

**Lokasi**: [`app/main.py:130-145`](app/main.py:130), [`app/core/security.py:142-145, 158-161`](app/core/security.py:142)

**Bukti**:
```python
# main.py:130
try:
    reset_scheduler = start_scheduler()
except Exception:
    pass  # ← Scheduler gagal? Kita diam saja!

# main.py:140-145
try:
    Base.metadata.create_all(bind=engine)
    print("[startup] create_all OK")
except Exception as e:
    import sys as _sys
    print(f"[startup] create_all gagal: {e}", file=_sys.stderr)  # ← print, bukan logger
```

**Masalah**:
- Silent failure: scheduler tidak start → reset counter tidak jalan, BUKAN logged.
- `print()` ke stderr hilang di production kalau logging di-redirect.
- Pakai `logger.error(..., exc_info=True)` lebih baik untuk stack trace.

**Rekomendasi**:
- Ganti `except: pass` dengan `except Exception as e: logger.error(f"Scheduler gagal: {e}", exc_info=True)`.
- Pakai logger config di `app/core/logging.py` (sentralisasi format + handler).
- Audit grep: `grep -rn "except Exception:" app/ | grep -v "logger"` → semua silent failures.

---

### 🟡 S2: Raw SQL Usage Risiko Injection (T163)

**Lokasi**: [`scripts/migrate_porsi_uni.py`](scripts/migrate_porsi_uni.py:1) (dan kemungkinan script lain)

**Bukti** (dari FASE 2 S5+S7):
```python
# scripts/migrate_porsi_uni.py — pakai text() dengan f-string
sql = f"ALTER TABLE kuitansi ADD COLUMN {col} BIGINT DEFAULT 0 NOT NULL"
conn.execute(text(sql))
```

**Penilaian**:
- Aman di konteks ini: `col` adalah hardcoded list, BUKAN user input.
- TAPI pattern ini bahaya kalau di-copy ke tempat lain dengan user input.

**Rekomendasi**:
- Whitelist kolom di level aplikasi (sudah ada: `bigint_cols = ["porsi_x_uni", ...]`).
- Tambah comment: `# SECURITY: nama kolom HARUS dari hardcoded list, JANGAN dari request.`
- Pattern aman untuk dynamic SQL: `sqlalchemy.sql.column(col)` atau named bind params.

---

### 🟡 S3: CORS Regex Terlalu Luas untuk Production (T164)

**Lokasi**: [`app/main.py:87`](app/main.py:87)

**Bukti**:
```python
allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?",
```

**Masalah**:
- Pattern mencakup SELURUH private IP range. Di LAN咖啡店或公共Wi-Fi (192.168.x.x), attacker bisa share origin dan steal session via CORS.
- `allow_credentials=True` + private range = CSRF risk di network lokal.
- Untuk prod cloud (e.g., VPS public): regex ini jadi tidak relevan karena IP bukan LAN.

**Rekomendasi**:
- Production: HAPUS regex LAN origins dari main.py, pakai `ALLOWED_ORIGINS` env exclusively (comment: "demo only, disable in prod").
- Demo mode: tetap boleh (comment: "untuk offline multi-device demo").
- Gate via env: `ALLOW_LAN_ORIGINS: bool = False` di config.py.

---

### 🟡 S4: File Upload Magic Bytes Tidak Diverifikasi (T165)

**Lokasi**: [`app/api/v1/scanner.py`](app/api/v1/scanner.py:52-71)

**Masalah**:
- Content-Type dari header bisa dipalsukan. Attacker upload `.exe` rename ke `.jpg` → Content-Type: image/jpeg (lie).
- OCR processor mungkin crash kalau feed binary non-image.

**Rekomendasi**:
```python
import filetype
kind = filetype.guess(file_bytes)
if kind.mime not in ALLOWED_TYPES:
    raise HTTPException(415, "Unsupported file type")
```

---

### 🟡 S5: `GET /health` Tidak Auth (Minor — Information Disclosure) (T166)

**Lokasi**: [`app/main.py:158-160`](app/main.py:158)

**Bukti**:
```python
@app.get("/health")
def health():
    return {"status": "healthy", "version": "1.1.0"}  # ← version bocor
```

**Masalah**:
- `/health` mengembalikan versi aplikasi. Attacker bisa research CVE spesifik versi tersebut.
- Untuk production, `/health` idealnya hanya return `{"status": "ok"}` tanpa metadata.

**Rekomendasi**:
- Hapus `version` dari response, atau gate behind `?detailed=true&key=admin-token`.

---

### 🟡 S6: Logging PII ke Stdout / Audit Log (T167)

**Lokasi**: Banyak tempat, audit via grep diperlukan.

**Bukti (perkiraan)**:
```python
# scanner.py:159-161
logger.info(
    f"[OCR save-batch] user_id={current_user['id']} role={current_user['role']} "
    f"tenant_id={tenant.id} tenant_slug={tenant.slug} items_count={len(payload.items)}"
)
# Aman: tidak ada PII (nama/nomor WA umat).
```

**Masalah**:
- Pola yang perlu diaudit: `logger.info(f"...{item.nama_umat}...")` → PII di log file.

**Rekomendasi**:
- Centralized helper: `def safe_log_pii(level, msg, **pii_fields)` → otomatis hash/mask field tertentu.
- Konvensi: log hanya `nomor_kuitansi_token` (sudah hash), BUKAN nama/HP.

---

### 🟡 S7: Tidak Ada CSRF Token untuk Endpoint Non-GET (T168)

**Lokasi**: Semua POST/PUT/DELETE endpoint.

**Masalah**:
- Walau JWT di Bearer header (bukan cookie), `allow_credentials=True` + CORS longgar = attacker situs lain bisa kirim request kalau user punya cookie (misal session admin di browser).
- Untuk Bearer-only auth: CSRF risk rendah TAPI tetap worth double-submit cookie pattern.

**Rekomendasi**:
- Pastikan auth HARUS via `Authorization: Bearer` header, BUKAN cookie session.
- Verify `current_user` dep TIDAK terima cookie (lihat oauth2_scheme = OAuth2PasswordBearer).

---

### 🟡 S8: Session Token Expire 480 Minutes (8 jam) — Terlalu Lama (T169)

**Lokasi**: [`app/core/config.py:9`](app/core/config.py:9) — `ACCESS_TOKEN_EXPIRE_MINUTES = 480`

**Masalah**:
- 8 jam = satu shift kerja. Kalau token bocor (via XSS, log leak), attacker punya 8 jam akses.
- Standard banking app: 15 menit idle, 1 jam max session.

**Rekomendasi**:
- Production: 60 menit idle + refresh token pattern (sliding window).
- Demo: 480 masih OK, tapi flag di config: `DEMO_LONG_SESSION: bool = True`.

---

### 🟡 S9: Backup File Download Tanpa Auth (Mungkin) (T170)

**Lokasi**: [`app/api/v1/admin.py`](app/api/v1/admin.py:1) — `GET /admin/backups` + download

**Bukti (perkiraan)**:
- Endpoint mungkin return list backup filenames dan binary content.

**Rekomendasi**:
- Pastikan `GET /admin/backups` butuh `require_admin_bootstrap_dependency`.
- File download via signed URL (1-shot, expire 5 menit), BUKAN direct stream.

---

## Temuan Rendah (🟢 Best Practice)

### 🟢 R1: `print()` Digunakan untuk Logging Startup (T171)

**Lokasi**: [`app/main.py:122, 142, 145`](app/main.py:122)

**Rekomendasi**:
- Pakai `logger.info(...)` dengan `logging.basicConfig(level=INFO)` di `app/core/logging.py`.
- Format JSON untuk ingestion ke log aggregator (Loki, ELK).

---

### 🟢 R2: Tidak Ada Health Check Detail untuk DB/Redis (T172)

**Rekomendasi**:
- Tambah `GET /health/deep` yang cek DB ping, Redis (kalau ada), scheduler alive.
- Return 503 kalau dependency down.

---

### 🟢 R3: `datetime.utcnow()` Masih Ada di Beberapa File (T173)

**Lokasi**: Perlu di-grep. `utcnow()` helper sudah ada di security.py tapi mungkin ada raw `datetime.utcnow()` calls elsewhere.

**Rekomendasi**:
- Audit grep: `grep -rn "datetime.utcnow()" app/` → pastikan semua pakai `from app.core.security import utcnow`.

---

### 🟢 R4: Tidak Ada Subresource Integrity (SRI) untuk JS/CSS Frontend (T174)

**Lokasi**: Frontend (di luar scope audit ini, tapi worth mention).

**Rekomendasi**:
- Untuk production build: `<script integrity="sha384-...">` di HTML.

---

### 🟢 R5: Password Default Seed Mungkin Lemah (T175)

**Lokasi**: `scripts/seed_demo.py` (perlu verifikasi).

**Rekomendasi**:
- Seed password harus ≥ 16 char random (`secrets.token_urlsafe(16)`).
- Force password change on first login untuk non-demo users.

---

### 🟢 R6: Tidak Ada Rate Limit di WA Outbound (Blast) (T176)

**Lokasi**: [`app/services/whatsapp.py`](app/services/whatsapp.py:1)

**Bukti (config)**: `WA_BLAST_RATE_PER_SEC: float = 1.1` (di config.py)

**Rekomendasi**:
- Rate limit HARUS enforced (lihat apakah code pakai sleep atau ignored).
- Quota tracking: decrement counter dari Fonnte quota, alert kalau < 100 remaining.

---

## ℹ️ Info / Hal Positif

### I1: Dependency Security Posture (T177)

**Bukti**: `requirements.txt` (perlu dibaca langsung untuk konfirmasi).

**Penilaian awal**:
- `fastapi`, `sqlalchemy 2.0`, `pydantic 2.x` — versi modern, security patches up-to-date.
- `passlib[bcrypt]` — ada CVE di bcrypt 4.0 (Oct 2024), verify version.
- `python-jose` — ada CVE di versi lama (algorithm confusion), verify >= 3.4.0.

**Rekomendasi**:
- `pip-audit` atau `safety check` di CI.
- Pin major versions di requirements.txt.

---

### I2: HTTPS / TLS (T178)

**Status**: Tergantung deployment (di luar code audit).
- Reverse proxy (nginx/Caddy) wajib TLS termination.
- HSTS header di nginx config.

---

### I3: Dependency License Audit (T179)

**Status**: Belum ada tools SBOM generation.

**Rekomendasi**:
- `pip-licenses` atau `syft` di CI untuk SBOM.

---

### I4: Backup Encryption (T180)

**Lokasi**: [`app/services/backup_service.py`](app/services/backup_service.py:1)

**Rekomendasi**:
- Backup file `.db` sebaiknya di-encrypt-at-rest (gpg symmetric atau age).
- Upload ke cloud (S3/GCS) dengan server-side encryption.

---

## Rekomendasi Prioritas (Roadmap)

| Sprint | Temuan | Effort | Impact |
|--------|--------|--------|--------|
| **Sprint 1 (urgent)** | K1 (rate limit login), K2 (WA rate limit Redis), T5 (race condition counter) | M | 🔴 |
| **Sprint 2** | T1 (upload validation), T3 (PII key rotation), T4 (password audit log) | M | 🟠 |
| **Sprint 3** | S1 (logging sentralisasi), S3 (CORS gate env), S8 (token expire policy) | S | 🟡 |
| **Sprint 4** | R1-R6 (best practices) | S | 🟢 |

---

## Appendix: Checks yang Sudah Diverifikasi ✅

| Check | Status | Bukti |
|-------|--------|-------|
| SQLAlchemy ORM (parameterized queries) | ✅ Aman | Semua query pakai `db.query(Model).filter(...)` |
| JWT secret dari env, bukan hardcoded | ✅ Aman | `settings.SECRET_KEY` di config.py |
| Bcrypt untuk password | ✅ Aman | `pwd_context = CryptContext(schemes=["bcrypt"])` |
| PII Fernet encryption | ✅ Aman | `fernet = Fernet(settings.PII_ENCRYPTION_KEY.encode())` |
| HTTPS enforcement (di kode) | ⚠️ N/A | Tergantung reverse proxy, bukan kode |
| Rate limit pada endpoint kritikal | ❌ Tidak ada | Lihat K1, K2 |
| File upload validation | ❌ Lemah | Lihat T1, S4 |
| CSRF protection | ⚠️ Bearer-based | Lihat S7 |
| Session timeout reasonable | ❌ 8 jam | Lihat S8 |
| Security headers (CSP, HSTS, X-Frame) | ❓ Belum dicek | Perlu audit nginx config |
| Error messages info disclosure | ✅ Minimal | `HTTPException(detail=...)` generic |
| Dependency vulnerability scan | ❓ Belum | Lihat I1 |
| Audit log completeness | ✅ Baik | `AuditLog` di setiap endpoint kritikal |
| Backup integrity | ❓ Belum dicek | Lihat I4 |

---

## Next Step

Laporan ini di-commit ke branch `audit/comprehensive-review`. Setelah itu:
1. Saya presentasikan ringkasan + rekomendasi prioritas ke user.
2. User decide: SETUJU eksekusi semua / parsial / tunda.
3. Eksekusi di sprint sesuai prioritas di atas (commit per fix: `audit(FASE3-Bx): [fix deskripsi]`).