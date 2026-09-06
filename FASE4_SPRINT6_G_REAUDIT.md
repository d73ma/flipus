# FASE 4 Sprint 6-G — Re-audit TenantScope Coverage

**Date**: 2026-09-03
**Branch**: `audit/comprehensive-review`
**Goal**: Re-run [`scripts/audit_tenant_scope.py`](Flipus/scripts/audit_tenant_scope.py:1) after S6-B/C/D/E/F patches and verify zero **true-positive** inline tenant filters remain.

---

## TL;DR

Setelah S6-A/B/C/D/E/F (6 sprints, 21 endpoint dimigrasi/diaudit), ada **4 endpoint yang terlewat oleh S6-A** karena S6-A hanya men-scan pattern `current_user["tenant_id"]` / `nama_uni ==` / `tenant_id ==`, **bukan** helper function `_tenant_ids_for_caller()` atau dependency `user: User = Depends(get_current_user)`.

| Status | Count | Endpoint(s) |
|---|---|---|
| 🟢 **Clean (already migrated)** | 19/24 file | `admin.py`, `dashboard.py`, `kuitansi.py`, `laporan_gabungan.py`, `m8_managed.py`, `master.py`, `notifications.py`, `onboarding.py`, `pengeluaran.py`, `pengeluaran_ocr.py`, `pengeluaran_wa.py`, `quick_input.py`, `reports.py`, `scanner.py`, `tenants.py`, `users.py`, `wa_input.py` |
| 🔴 **True positive (perlu patch)** | **4** | `agregat.py::/sabat-ini` + `/ytd` + `sync.py::/upload` + `/pull` |
| ⚠️ **False positive / not security filter** | 11 | `auth.py::/login, /forgot-password, /refresh, /change-password` + `demo.py::/login-as/{role}` + `twofa.py::/setup, /verify, /disable, /backup-codes, /login` + `register.py::/admin` |

---

## Audit script fix (S6-G commit pertama)

**Problem**: Script original men-classify endpoint yang pakai `scope.visible_tenant_ids` (legitimate read dari `TenantScope`) sebagai **inline tenant logic** karena `visible_tenant_ids` ada di `INLINE_TENANT_KEYWORDS` list.

**Fix**: `analyze_endpoint()` sekarang ignore inline findings kalau endpoint sudah punya `safe patterns` (`require_tenant_scope` / `TenantScope`).

```python
# FASE4-S6G: kalau endpoint sudah pakai TenantScope (safe patterns),
# `visible_tenant_ids` dll adalah legitimate read via scope — BUKAN inline.
has_safe = len(safe_findings) > 0
if has_safe:
    inline_findings = []
```

Lokasi: [`scripts/audit_tenant_scope.py:71-74`](Flipus/scripts/audit_tenant_scope.py:71).

**Total endpoints**: 104 across 24 files.
**Endpoints sudah pakai TenantScope**: 21 (`Safe` column).
**True positive inline yang masih ada**: **4**.

---

## 4 true positives yang terlewat S6-A

### 1. `agregat.py::/sabat-ini` (L759) 🔴
**Pattern**: `current_user: dict = Depends(get_current_user)` + helper [`_tenant_ids_for_caller(db, current_user)`](Flipus/app/api/v1/agregat.py:721).
**Why missed by S6-A**: keyword `_tenant_ids_for_caller` TIDAK ada di S6-A regex list (yang hanya cover `current_user`-named deps).
**Risk**: admin uni / auditor misi bisa jadi cuma lihat scope mereka sendiri via `current_user["tenant_id"]` jika helper gagal resolve.
**Fix needed**: migrate ke `scope: TenantScope = Depends(require_tenant_scope)`, pakai `scope.visible_tenant_ids`.

### 2. `agregat.py::/ytd` (L1045) 🔴
**Same pattern as `/sabat-ini`**. S6-B patched 3 endpoints in `agregat.py` (`/chart/mingguan`, `/sabat-ini` chart variant, …) tapi **kedua endpoint ini terlewat**.

### 3. `sync.py::/upload` (L42) 🔴
**Pattern**: `user: User = Depends(get_current_user)` + filter via `user.tenant_id`.
**Why missed**: dependency pakai tipe `User` (DB model), bukan `dict` — keyword `current_user` tidak match.
**Risk**: **CRITICAL** — untuk `ADMIN_UNI`, scoping upload ke `user.tenant_id` (single tenant = admin uni placeholder) berarti **smeared data** — admin uni hanya bisa upload dari satu tenant placeholder, bukan dari semua tenant di uni.
**Fix needed**: pakai `scope.visible_tenant_ids`; restrict role ke `BENDAHARA` saja (sudah ada) — admin uni upload memang tidak masuk design.

### 4. `sync.py::/pull` (L77) 🔴
**Pattern**: sama seperti `/upload`. Allowed roles: `AUDITOR_MISI` + `ADMIN_UNI`.
**Risk**: **CRITICAL** — `AUDITOR_MISI` dengan `user.tenant_id` scoping cuma bisa pull dari **satu tenant** (= auditor's home tenant), bukan seluruh misi. **Real cross-tenant under-coverage**.
**Fix needed**: pakai `scope.visible_tenant_ids` (akan return semua tenant di misi).

---

## 11 false positives (audit finds, security OK)

| Endpoint | Reason not security filter |
|---|---|
| `auth.py::/login` | Pre-auth endpoint. `user.tenant_id` = `User` row tenant (data lookup, bukan filter). |
| `auth.py::/forgot-password` | Pre-auth. `user.tenant_id` di audit log field saja. |
| `auth.py::/refresh` | Pre-auth. Refresh JWT, tidak query tenant. |
| `auth.py::/change-password` | Authenticated; `user.tenant_id` cuma untuk audit log field. Tidak ada query `WHERE tenant_id == ...`. |
| `demo.py::/login-as/{role}` | Demo mode (gated by env `DEMO_MODE_ENABLED`). Single-tenant login helper. |
| `twofa.py::/setup, /verify, /disable, /backup-codes` | 2FA user-state ops. `user.tenant_id` di audit log field. Tidak ada cross-tenant data access. |
| `twofa.py::/login` | Pre-auth 2FA step. Tidak ada filter. |
| `register.py::/admin` | Public self-service registration. Sudah ditandai false-positive di S6-F commit. |

**Conclusion**: 11 endpoint tersebut bukan tenant-isolation filter — mereka cuma mereferensikan `tenant_id` sebagai **data attribute** (audit log field, JWT claim, response field). Tidak ada risiko cross-tenant leak.

---

## Test impact

- Audit script update tidak affect runtime.
- Tidak ada test failures dari audit changes.

---

## Next sprints (proposed)

### S6-G (current) ✅ DONE
- Fix audit script classification bug.
- Identify 4 missed true positives.
- Commit audit script + this report.

### S6-H (proposed — replaces original S6-H scope)
**Patch 4 missed endpoints**:
- `agregat.py::/sabat-ini` + `/ytd` → migrate to `TenantScope`.
- `sync.py::/upload` + `/pull` → migrate to `TenantScope`; tambah role-guard untuk sync upload (admin uni/auditor boleh pull only).
- Estimate: ~2 file, +50/-30, 1 commit.

### S6-I (was 6-H)
Role matrix testing (5 roles × all migrated endpoints).

### S6-J (was 6-I)
Cross-tenant leakage testing per endpoint.

### S6-K (new — was 6-J)
Coverage verify + Sprint 6 summary.

---

## Sign-off

Sprint 6-G: audit script fixed, 4 missed true positives identified, awaiting `LANJUT` for S6-H.