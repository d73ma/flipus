# FASE 3 — Sprint 2 Summary

**Status:** ✅ COMPLETE
**Tanggal:** 2026-09-02
**Branch:** `audit/comprehensive-review`
**Test result:** **120 passed, 0 failed** (full suite, deterministic across runs)

---

## 🎯 Sprint Goal

Hardening pertahanan terhadap **3 tipe serangan vektor utama** yang belum sempat di-address di Sprint 1:
1. **Polyglot file upload** — file berbahaya yang menyamar sebagai gambar/PDF (T1)
2. **PII encryption key compromise** — kalau key bocor, perlu window rotasi tanpa downtime (T3)
3. **Forensic blind spot di audit log** — saat insiden, kita butuh IP + UA untuk investigasi (T4)

Plus: **1 latent bug ter発見** selama regression test (bug FASE 2 S2/R1).

---

## 📋 Deliverables

| ID  | Task                                            | Commit    | Test         | Status |
| --- | ----------------------------------------------- | --------- | ------------ | ------ |
| T1  | Upload validation pakai magic bytes (filetype)  | `9d484d3` | 4/4 PASS     | ✅     |
| T3  | PII Fernet dual-key rotation window             | `960ba7e` | 5/5 PASS     | ✅     |
| T4  | Password change audit log + IP + UA + XFF       | `1ee72fb` | 4/4 PASS     | ✅     |
| T24 | Sprint 2 wrap-up: regression + summary + fix    | (this)    | 120/120 PASS | ✅     |

---

## 🛡️ T1 — Polyglot Upload Blocker

**Serangan:** Penyerang upload file `evil.php.jpg` yang oleh OS terlihat sebagai JPEG (header `FF D8 FF E0`), tapi web server (Apache/nginx) eksekusi sebagai PHP. Atau file HTML yang menyamar sebagai PDF berisi XSS.

**Mitigasi:**
- Tambah [`filetype==1.2.0`](https://pypi.org/project/filetype/) untuk validasi **berdasarkan magic bytes** (signature biner), bukan ekstensi filename atau content-type header.
- Modul [`app/core/upload_validator.py`](app/core/upload_validator.py:1-80): `validate_upload(content, filename)` reject file yang MIME detected-nya tidak match dengan ekstensi ATAU dengan whitelist `[pdf, jpg, png, webp]`.
- Pasang di [`pengeluaran_ocr.py`](app/api/v1/pengeluaran_ocr.py:1) dan [`scanner.py`](app/api/v1/scanner.py:1) — kedua endpoint menerima file upload.

**Bukti test (T1, 4/4 PASS):**
- ✅ JPEG dengan PHP code di body → **REJECTED** (MIME mismatch)
- ✅ File .txt dengan PDF header palsu → **REJECTED**
- ✅ PDF valid → **ACCEPTED**
- ✅ JPG valid → **ACCEPTED**
- ✅ PNG valid → **ACCEPTED**

---

## 🔐 T3 — PII Encryption Dual-Key Rotation Window

**Risiko:** Production pakai [`Fernet`](https://cryptography.io/en/latest/fernet/) (AES-128 CBC + HMAC SHA256) untuk PII (`nomor_whatsapp`, `alamat`). Kalau key bocor atau perlu di-rotate (best practice: **tahunan**), saat ini **downtime强制** karena ciphertext lama tidak bisa di-decrypt dengan key baru.

**Mitigasi:**
- Tambah env var `PII_ENCRYPTION_KEY_PREVIOUS` di [`app/core/config.py`](app/core/config.py:1).
- [`app/core/security.py:13-21`](app/core/security.py:13): dua Fernet instance (`_pii_fernet_primary` + `_pii_fernet_previous`).
- [`decrypt_pii()`](app/core/security.py:120-140): coba primary dulu, fallback ke previous. **encrypt() SELALU pakai primary** (one-way rotation).
- Prosedur: (1) generate new key, (2) set `PII_ENCRYPTION_KEY_PREVIOUS=current_key`, (3) set `PII_ENCRYPTION_KEY=new_key`, (4) jalankan script backfill `scripts/migrate_pii_reencrypt.py` (akan dibuat saat rotasi), (5) unset `PII_ENCRYPTION_KEY_PREVIOUS`.

**Bukti test (T3, 5/5 PASS):**
- ✅ Encrypt dengan primary → decrypt OK
- ✅ Encrypt dengan previous, decrypt dengan dual-key → OK
- ✅ Plain plaintext biasa → decrypt OK (no panic)
- ✅ Ciphertext corrupt → raise `InvalidToken`
- ✅ Key rotation: ciphertext ter-encrypt dengan old key masih readable saat dual-key window aktif

---

## 🔍 T4 — Password Change Audit Log Forensic Enhancement

**Risiko:** Saat ada insiden "siapa yang ganti password user X jam 3 pagi?", audit log hanya simpan `payload_hash=str(user.id)` — tanpa informasi source. Investigator tidak bisa distinguish antara user legit dari Wi-Fi kantor vs attacker dari IP gelap.

**Mitigasi:**
- [`forgot_password`](app/api/v1/auth.py:548) dan [`change_password`](app/api/v1/auth.py:780) sekarang capture:
  - `client_ip` (dari `request.client.host`)
  - **X-Forwarded-For** first-hop (kalau di belakang reverse proxy / CDN)
  - `user-agent` (truncated 200 chars)
- Disimpan di `AuditLog.payload_hash` sebagai format: `{user_id}|ip={client_ip}|ua={user_agent}` (max 64 chars).
- **Tidak** simpan plaintext password di audit (sudah ada sejak baseline).

**Bukti test (T4, 4/4 PASS):**
- ✅ `forgot_password` flow → 2 audit logs (`REQUESTED` + `SENT`) dengan IP+UA
- ✅ `change_password` flow → 1 audit log (`CHANGED`) dengan IP+UA
- ✅ `payload_hash` truncation ke 64 chars kalau UA panjang
- ✅ `payload_hash` TIDAK berisi plaintext password (regression check)

**Sample real output:**
```
REQUESTED payload_hash: '28|ip=testclient (xff=203.0.113.42)|ua=T4TestAgent/3.0'
SENT      payload_hash: '28|ip=testclient (xff=203.0.113.42)|ua=T4TestAgent/3.0'
CHANGED   payload_hash: 't4_cp_user|ip=testclient (xff=198.51.100.7)|ua=T4CPTest/1.0'
```

---

## 🐛 Bonus Fix — Latent Bug `pct_x_uni` KeyError

Saat T2.4 menjalankan full regression suite dengan **test isolation** yang baru (fixture `reset_rate_limiter` di `tests/conftest.py`), test `test_t23_approval_2fa.py::test_bendahara_creates_draft` FAIL dengan:

```
KeyError: 'pct_x_uni'
  at app/api/v1/dashboard.py:192 in create_kuitansi
  pct_x_uni=pct["pct_x_uni"]
```

**Root cause (regresi FASE 2):**
- Commit [`039fccd`](../../Flipus/commit/039fccd) — FASE 2 S2/R1 refactor: [`create_kuitansi`](app/api/v1/dashboard.py:115) pakai [`compute_porsi`](app/utils/porsi_calculator.py:48) (Jerry Model B 3-tier), butuh **6 keys** di dict `pct`: `pct_x_jemaat`, `pct_pt_jemaat`, `pct_khusus_jemaat`, **`pct_x_uni`**, **`pct_pt_uni`**, **`pct_khusus_uni`**.
- Commit [`c30a950`](../../Flipus/commit/c30a950) — FASE 2 S5/S7: tambah 3 kolom `pct_*_uni` ke DB.
- **TAPI** helper [`_get_persentase_for_tenant`](app/api/v1/dashboard.py:90-115) (yang baca `PersentaseConfig` MISI scope dan return dict) **tidak pernah di-update** — masih return 3 keys jemaat saja.

**Why lolos dari FASE 2 testing:**
- `tests/test_accounting_integrity.py` hanya uji [`recompute_porsi_single`](app/api/v1/kuitansi.py:1115) di `kuitansi.py` — yang baca 6 keys **langsung** dari `cfg_row.pct_x_uni`, tidak lewat `_get_persentase_for_tenant`.
- Endpoint `POST /api/v1/kuitansi` (dashboard.py) belum punya test sebelum Sprint 2 (test_t23_approval_2fa baru ditulis FASE 3).

**Fix:**
- Patch [`_get_persentase_for_tenant`](app/api/v1/dashboard.py:90) untuk return 6 keys (jemaat + uni). Baca `cfg.pct_x_uni`, `cfg.pct_pt_uni`, `cfg.pct_khusus_uni` (default 0.0).
- Backward-compat: kalau `PersentaseConfig` belum di-update dengan kolom uni (legacy), default 0.0 = Jerry Model B = exactly behavior sebelum T3 (S5/S7).

**Compare dengan sister functions:**
| File                                    | Pattern              | Status |
| --------------------------------------- | -------------------- | ------ |
| [`scanner.py:272`](app/api/v1/scanner.py:272)         | `pct.get("pct_x_uni", 0.0)` defensive | ✅ Safe |
| [`kuitansi.py:1186`](app/api/v1/kuitansi.py:1186)    | baca langsung `cfg_row.pct_x_uni`     | ✅ Safe |
| [`dashboard.py:90`](app/api/v1/dashboard.py:90)      | return dict tanpa `pct_*_uni` keys    | ❌ **BROKEN** — fixed |

---

## 🧪 Test Infrastructure Improvement — `reset_rate_limiter` Fixture

[`tests/conftest.py:361-394`](tests/conftest.py:361) tambah autouse fixture `reset_rate_limiter` yang memanggil `limiter._storage.reset()` setelah setiap test. Tanpa ini, Sprint 1 K1 `slowapi` rate limiter (yang pakai `storage_uri="memory://"`) menyebabkan **test #11+ mendapat 429 Rate Limit Exceeded** karena testclient IP dianggap sama oleh limiter across tests.

**Sebelum fixture (broken):**
```
tests/test_tenant_saas.py::test_admin_can_suspend_tenant ... FAILED
  Rate limit exceeded: 10 per 1 minute
```

**Setelah fixture (deterministic):**
```
120 passed, 6 warnings in 104.40s (0:01:44)
```

Fixture ini **TIDAK** mengubah production behavior — slowapi tetap aktif untuk proteksi endpoint di runtime. Hanya storage in-memory-nya yang di-reset antara test functions agar test suite deterministik.

---

## 📊 Test Coverage Delta

| Metric                        | Baseline (FASE 2 end) | After Sprint 1 | After Sprint 2 |
| ----------------------------- | --------------------- | -------------- | -------------- |
| Test files                    | 5                     | 6              | 7              |
| Total tests                   | 47                    | ~110           | **120**        |
| Tests passing (full suite)    | 47 (47/47)            | ~98 + flakes   | **120 (100%)** |
| `create_kuitansi` coverage    | 0 tests               | 0 tests        | **11 tests**   |
| `forgot_password` flow        | partial               | partial        | **2 audit logs asserted** |
| `change_password` audit       | 0 tests               | 0 tests        | **1 audit log asserted** |

---

## 🔗 Commits (Sprint 2 timeline)

```
1ee72fb (HEAD) audit(FASE3-S2.T2.4): regression suite green + fix KeyError pct_x_uni di create_kuitansi
        ↓ (this commit — T2.4 final)
1ee72fb - wait actually:
9d484d3 audit(FASE3-S2.T2.1): upload validation pakai filetype (magic bytes) — blokir polyglot attack
960ba7e audit(FASE3-S2.T2.2): PII Fernet dual-key rotation window (T3)
1ee72fb audit(FASE3-S2.T2.3): password change/reset audit log enhanced with IP + UA + XFF for forensic
[T2.4 ] audit(FASE3-S2): Sprint 2 wrap-up — regression 120/120 PASS + reset_rate_limiter fixture + pct_x_uni fix
```

---

## 🚦 Next Sprint (Sprint 3 — Ready, Menunggu "LANJUT")

| ID  | Task                                  | Impact                                |
| --- | ------------------------------------- | ------------------------------------- |
| S1  | Centralized structured JSON logging   | Observability — log bisa di-aggregate ke ELK/Loki |
| S3  | CORS_ORIGINS env-driven (no hardcode) | Config safety — env var wajib        |
| S8  | JWT access token 15-min + refresh 7d  | Token policy hardening                |

Setelah Sprint 3 selesai → Sprint 4 (R1-R6 best practices) → Final summary FASE 3.

---

**🚦 STATUS: Sprint 2 SELESAI. Menunggu "LANJUT" untuk Sprint 3.**