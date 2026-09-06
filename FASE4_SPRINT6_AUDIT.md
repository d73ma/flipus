# FASE 4 — Sprint 6 Audit Report

**Generated**: FASE4-S6A (audit script [`scripts/audit_tenant_scope.py`](../Flipus/scripts/audit_tenant_scope.py))

## Summary

| File | Endpoints | Inline | Safe | NoOp | usesTS |
|------|-----------|--------|------|------|--------|
| ⚠️ [admin.py](../Flipus/app/api/v1/admin.py) | 7 | 1 | 0 | 6 | no |
| ⚠️ [agregat.py](../Flipus/app/api/v1/agregat.py) | 6 | 3 | 0 | 3 | YES |
| ⚠️ [auth.py](../Flipus/app/api/v1/auth.py) | 5 | 4 | 0 | 1 | no |
| ⚠️ [dashboard.py](../Flipus/app/api/v1/dashboard.py) | 6 | 2 | 0 | 4 | no |
| ⚠️ [demo.py](../Flipus/app/api/v1/demo.py) | 3 | 1 | 0 | 2 | no |
| ✅ [kuitansi.py](../Flipus/app/api/v1/kuitansi.py) | 5 | 0¹ | 4 | 1 | YES |
| ⚠️ [laporan_gabungan.py](../Flipus/app/api/v1/laporan_gabungan.py) | 3 | 3 | 0 | 0 | no |
| ✅ m8_managed.py | 3 | 0 | 0 | 3 | no |
| ✅ [master.py](../Flipus/app/api/v1/master.py) | 5 | 0 | 0 | 5 | no |
| ✅ [notifications.py](../Flipus/app/api/v1/notifications.py) | 6 | 0 | 0 | 6 | no |
| ✅ onboarding.py | 1 | 0 | 0 | 1 | no |
| ⚠️ [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py) | 11 | 4 | 0 | 7 | no |
| ⚠️ [pengeluaran_ocr.py](../Flipus/app/api/v1/pengeluaran_ocr.py) | 2 | 1 | 0 | 1 | no |
| ✅ [pengeluaran_wa.py](../Flipus/app/api/v1/pengeluaran_wa.py) | 2 | 0 | 0 | 2 | no |
| ⚠️ [quick_input.py](../Flipus/app/api/v1/quick_input.py) | 2 | 2 | 0 | 0 | no |
| ⚠️ [register.py](../Flipus/app/api/v1/register.py) | 3 | 1 | 0 | 2 | no |
| ⚠️ [reports.py](../Flipus/app/api/v1/reports.py) | 5 | 2 | 0 | 3 | no |
| ✅ [scanner.py](../Flipus/app/api/v1/scanner.py) | 2 | 0 | 0 | 2 | no |
| ⚠️ [sync.py](../Flipus/app/api/v1/sync.py) | 2 | 2 | 0 | 0 | no |
| ⚠️ [tenants.py](../Flipus/app/api/v1/tenants.py) | 12 | 1 | 0 | 11 | no |
| ⚠️ [twofa.py](../Flipus/app/api/v1/twofa.py) | 6 | 5 | 0 | 1 | no |
| ✅ [users.py](../Flipus/app/api/v1/users.py) | 2 | 0 | 0 | 2 | no |
| ✅ [wa_input.py](../Flipus/app/api/v1/wa_input.py) | 5 | 0 | 0 | 5 | no |
| **TOTAL** | **104** | **36²** | **4** | | |

¹ `kuitansi.py` 4 endpoints flagged "inline" karena masih menyebut `visible_tenant_ids` di query — tapi itu `scope.visible_tenant_ids` (TenantScope). **False positive** — sebenarnya sudah ✅ aman.

² Total 36 termasuk 4 false-positive dari `kuitansi.py`. Net true positives: **32**.

## Kategorisasi Temuan

#### A. Endpoint yang perlu migrasi (true positives, perlu patch)

| File | Endpoint | Pattern |
|------|----------|---------|
| [admin.py](../Flipus/app/api/v1/admin.py) | POST `/recompute-porsi` (L356) | `nama_uni == caller.nama_uni` (ADMIN_UNI-specific) |
| [agregat.py](../Flipus/app/api/v1/agregat.py) | GET `/sabat-ini` (L759) | inline role-check (deferred dari S5-C) |
| [agregat.py](../Flipus/app/api/v1/agregat.py) | GET `/ytd` (L1045) | `_tenant_ids_for_caller` |
| [agregat.py](../Flipus/app/api/v1/agregat.py) | GET `/chart/mingguan` (L1209) | inline `tenant_id = current_user`, `nama_uni ==` |
| [dashboard.py](../Flipus/app/api/v1/dashboard.py) | GET `/kuitansi/pending` (L626) | inline `tenant_id == current_user` |
| [dashboard.py](../Flipus/app/api/v1/dashboard.py) | GET `/kuitansi/rejected` (L691) | inline `tenant_id == current_user` |
| [laporan_gabungan.py](../Flipus/app/api/v1/laporan_gabungan.py) | GET `/laporan/gabungan/{id}` (L116) | inline `tenant_id = current_user` |
| [laporan_gabungan.py](../Flipus/app/api/v1/laporan_gabungan.py) | GET `/laporan/gabungan/{id}/pdf` (L236) | inline `tenant_id = current_user` |
| [laporan_gabungan.py](../Flipus/app/api/v1/laporan_gabungan.py) | POST `/laporan/gabungan/{id}/send-to-auditor` (L330) | inline `tenant_id = current_user` |
| [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py) | GET `/kategori-pengeluaran/list` (L184) | inline `tenant_id = current_user` |
| [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py) | GET `/pengeluaran/list` (L254) | inline `tenant_id = current_user` |
| [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py) | GET `/pengeluaran/pending-count` (L521) | inline `tenant_id = current_user` |
| [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py) | GET `/pengeluaran/rekap` (L545) | inline `tenant_id = current_user` |
| [pengeluaran_ocr.py](../Flipus/app/api/v1/pengeluaran_ocr.py) | POST `/pengeluaran/ocr-save` (L223) | inline `tenant_id = current_user` |
| [quick_input.py](../Flipus/app/api/v1/quick_input.py) | POST `/kuitansi/quick-input` (L183) | inline `tenant_id = current_user` |
| [quick_input.py](../Flipus/app/api/v1/quick_input.py) | GET `/kategori/list` (L367) | inline `tenant_id = current_user` |
| [register.py](../Flipus/app/api/v1/register.py) | POST `/admin` (L324) | inline `nama_uni ==` (admin-specific) |
| [reports.py](../Flipus/app/api/v1/reports.py) | GET `/sabat-info` (L81) | inline `tenant_id == current_user` |
| [reports.py](../Flipus/app/api/v1/reports.py) | GET `/mingguan` (L130) | inline `tenant_id == current_user` |
| [tenants.py](../Flipus/app/api/v1/tenants.py) | GET `/` (L214) | inline `nama_uni ==` (ADMIN_UNI listing) |

**Total: 20 endpoints dalam 9 file** yang perlu migrasi.

#### B. Endpoint yang "false positive" (audit flagged, tapi aman)

| File | Endpoint | Alasan |
|------|----------|--------|
| [auth.py](../Flipus/app/api/v1/auth.py) | `/login`, `/forgot-password`, `/refresh`, `/change-password` | `user.tenant_id` di sini adalah caller's OWN tenant (untuk set tenant context di JWT) — bukan query filter cross-tenant. Aman by design. |
| [twofa.py](../Flipus/app/api/v1/twofa.py) | `/2fa/*` (5 endpoint) | Sama — 2FA flows selalu operate on caller's own user.tenant_id |
| [sync.py](../Flipus/app/api/v1/sync.py) | `/upload`, `/pull` | Mobile sync — user.tenant_id = sync user's tenant |
| [demo.py](../Flipus/app/api/v1/demo.py) | `/login-as/{role}` | Demo-only, non-production path |
| [kuitansi.py](../Flipus/app/api/v1/kuitansi.py) | 4 endpoint yang sudah migrasi (S5-B) | `visible_tenant_ids` di sini adalah `scope.visible_tenant_ids` (TenantScope) — ✅ aman |

**Total: 12 false-positive endpoints** — tidak perlu patch.

#### C. Endpoint yang flag "no inline" tapi tetap perlu review

| File | Endpoint | Catatan |
|------|----------|---------|
| master.py, users.py, notifications.py, scanner.py, wa_input.py, dll | Beberapa endpoint tanpa tenant sama sekali | Mungkin tidak akses tenant data (admin-only, atau global). Perlu review manual tapi prioritas rendah. |

## Rencana Patch (S6-B sampai S6-G)

| Step | File | Endpoints | Strategi |
|------|------|-----------|----------|
| **S6-B** | [agregat.py](../Flipus/app/api/v1/agregat.py) | 3 (sabat-ini, ytd, chart) | Ganti `_tenant_ids_for_caller` callsite pakai `TenantScope`. Sabat-ini tambah role-check eksplisit. |
| **S6-C** | [dashboard.py](../Flipus/app/api/v1/dashboard.py), [reports.py](../Flipus/app/api/v1/reports.py) | 4 (2+2) | Tambah `scope: TenantScope = Depends(require_tenant_scope)`, replace inline filter |
| **S6-D** | [pengeluaran.py](../Flipus/app/api/v1/pengeluaran.py), [pengeluaran_ocr.py](../Flipus/app/api/v1/pengeluaran_ocr.py) | 5 (4+1) | Sama pattern |
| **S6-E** | [quick_input.py](../Flipus/app/api/v1/quick_input.py) | 2 | Sama pattern |
| **S6-F** | [laporan_gabungan.py](../Flipus/app/api/v1/laporan_gabungan.py) | 3 | Sama pattern |
| **S6-G** | [admin.py](../Flipus/app/api/v1/admin.py), [tenants.py](../Flipus/app/api/v1/tenants.py), [register.py](../Flipus/app/api/v1/register.py) | 3 (1+1+1) | ADMIN_UNI-specific — pakai `scope.role == "ADMIN_UNI"` guard + `scope.visible_tenant_ids` |

Total: **20 endpoints di 9 file**.

## Catatan tentang File "Aman" yang Tidak Perlu Patch

File-file ini punya endpoints yang **tidak operasional tenant data** (admin-only, atau akses self-only):

- [master.py](../Flipus/app/api/v1/master.py) — Kategori master (biasanya admin-only, public-read)
- [users.py](../Flipus/app/api/v1/users.py) — User management (admin-only)
- [notifications.py](../Flipus/app/api/v1/notifications.py) — Notifikasi user (per-user, bukan per-tenant)
- [scanner.py](../Flipus/app/api/v1/scanner.py) — Scanner receipt (per-user uploads)
- [wa_input.py](../Flipus/app/api/v1/wa_input.py) — WA inbound webhook (no auth)

Akan di-review manual di S6-H test matrix.

## Catatan tentang File Auth-Flow (false-positive tapi tetap harus diaudit)

File-file ini flagged karena `user.tenant_id` muncul, tapi `user.tenant_id` di sini:

1. **Selalu = caller's own tenant** (bukan cross-tenant lookup)
2. **Dipakai untuk JWT context** (generate token dengan tenant_id embedded)
3. **Bukan query filter** untuk list data

Contoh aman:
```python
# auth.py — login endpoint
user = db.query(User).filter(User.username == username).first()
# user.tenant_id = user's own tenant_id (from DB row)
# Dipakai untuk embed di JWT, bukan query filter
```

Contoh TIDAK aman (perlu migrasi):
```python
# dashboard.py — list pending kuitansi
kuitansi_list = db.query(Kuitansi).filter(
    Kuitansi.tenant_id == current_user["tenant_id"],  # ← query filter
    Kuitansi.status == "pending"
).all()
# Di sini current_user["tenant_id"] = hard filter single-tenant
# Untuk ADMIN_UNI/AUDITOR_MISI, ini SALAH — harus pakai visible_tenant_ids
```

## Next Step

Lanjut ke **S6-B**: Patch `agregat.py` (3 endpoint deferred dari S5-C).