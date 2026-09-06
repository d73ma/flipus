# FASE 3 Sprint 1 — Summary Report

**Branch:** `audit/comprehensive-review`
**Period:** Sprint 1 of 4 (FASE 3 — Audit Bug, Error, & Celah Keamanan)
**Status:** ✅ **COMPLETE** — 3 rekomendasi diimplementasi & diverifikasi

---

## 🎯 Rekomendasi yang Dieksekusi

| ID   | Judul                                              | Severity | Commit    | Status |
| ---- | -------------------------------------------------- | -------- | --------- | ------ |
| K1   | Login brute force (slowapi 10/min)                 | 🔴 High  | `6d14faa` | ✅     |
| K2   | WA webhook spam (slowapi 1/2sec per phone)         | 🔴 High  | `e536248` | ✅     |
| T5   | Race condition di `scanner.save_ocr_batch`         | 🔴 High  | `3a9f227` | ✅     |

---

## 📋 Detail Implementasi

### K1 — Login Brute Force Protection (`6d14faa`)

**File diubah:**
- `app/core/rate_limiter.py` (BARU) — slowapi `Limiter` instance dengan 2 key_funcs
- `app/main.py` — wire `app.state.limiter`, tambahkan `RateLimitExceeded` exception handler
- `app/api/v1/auth.py` — limit `/login` (10/min) dan `/forgot-password` (3/min) by IP

**Strategi:**
- `key_func=_key_func_by_ip` (default) untuk auth endpoints (limit per IP address)
- `headers_enabled=False` (FLIPUS endpoints return Pydantic, bukan `Response`)
- `storage_uri="memory://"` (cukup untuk single-worker SQLite; dokumentasi Redis untuk multi-worker)
- 429 JSON response dengan `Retry-After` header

**Verifikasi:**
- 47 unit tests pass (29 accounting + 18 branding)
- Pre-existing T24 test isolation issue tidak terkait dengan perubahan ini (verified via git stash baseline)

---

### K2 — WA Webhook Spam Protection (`e536248`)

**File diubah:**
- `app/api/v1/wa_input.py` — `_set_wa_from_state` `Depends()` yang populate `request.state.wa_from` dari form/JSON body, lalu `@_rate_limiter.limit("1/2seconds", key_func=_key_func_by_phone)`

**Strategi:**
- `key_func=_key_func_by_phone` baca `request.state.wa_from`, fallback ke IP
- Limit per-nomor-WA, bukan per-IP — satu IP (misal corporate NAT) boleh submit banyak nomor berbeda tanpa konflik
- 1 request per 2 detik per phone = 30/menit per phone (reasonable untuk user riil)

**Verifikasi:**
- 47 unit tests pass
- Pre-existing T24 test isolation issue (terkonfirmasi pre-existing, bukan regresi)

---

### T5 — Race Condition di `save_ocr_batch` (`3a9f227`)

**File diubah:**
- `app/api/v1/scanner.py` — wrap per-item `db.flush()` dalam SAVEPOINT (`db.begin_nested()`), catch `IntegrityError` dari UNIQUE constraint `nomor_kuitansi`, retry max 5× dengan increment `urutan` dan jitter 10-50ms

**Strategi:**
- Plain `db.rollback()` akan kehilangan SEMUA item dalam batch → SALAH
- SAVEPOINT (`begin_nested()`) rollback HANYA item yang conflict → item lain yang sudah inserted tetap aman
- Bounded retry (5×) untuk mencegah infinite loop di bawah contention tinggi
- Jitter untuk kurangi thundering herd (multiple Bendahara submit bersamaan)

**Verifikasi:**
- ✅ Concurrency test PASS: 5 threads racing di `urutan=1`, semua dapat `nomor_kuitansi` unik (002-006), 6 rows di DB (1 pre-seed + 5 workers)
- 47 unit tests pass

---

## 📊 Statistik Perubahan

```
Commit    Files    Insertions    Deletions
6d14faa   4        ~80           ~30
e536248   1        ~49           ~22
3a9f227   1        ~51           ~2
────────────────────────────────────────
Total     6        ~180          ~54
```

**Files modified:**
- `requirements.txt` (slowapi==0.1.9, limits[redis]==3.13.0, filetype==1.2.0, python-magic==0.4.27)
- `app/core/rate_limiter.py` (BARU)
- `app/main.py`
- `app/api/v1/auth.py`
- `app/api/v1/wa_input.py`
- `app/api/v1/scanner.py`

---

## ✅ Verification Matrix

| Test type                | Count  | Status |
| ------------------------ | ------ | ------ |
| Unit test accounting     | 29     | ✅ PASS |
| Unit test branding       | 18     | ✅ PASS |
| Concurrency stress (T5)  | 5 thr  | ✅ PASS |
| Pre-existing test issue  | (T24)  | ⚠️ Unchanged — bukan regresi |

---

## ⏭️ Sprint 2 Preview

Rekomendasi yang akan dieksekusi di Sprint 2:
- **T1** — Upload validation dengan `filetype` (magic bytes) untuk blokir polyglot/disguised files
- **T3** — PII encryption key rotation (dual-key window)
- **T4** — Password change audit log

Estimasi: 3 file utama + 3 commit + concurrency test untuk key rotation.

---

**Sprint 1 status:** ✅ COMPLETE — moving to Sprint 2.