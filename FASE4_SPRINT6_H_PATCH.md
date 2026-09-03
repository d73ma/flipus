# FASE 4 Sprint 6-H — Patch 4 Missed True Positives

**Branch:** `audit/comprehensive-review`
**Tanggal:** 2026-09-03
**Prioritas:** P0 (terutama `sync.py::/pull` yang punya **cross-tenant under-coverage** real)
**Status:** ✅ COMPLETE — 4/4 patched, audit clean, 397/397 tests pass

---

## Latar Belakang

Sprint 6-G (commit `de52d55`) menemukan **4 true positives** yang luput dari
regex S6-A:

| File | Endpoint | Pattern yang missed |
|---|---|---|
| [`agregat.py::/sabat-ini`](app/api/v1/agregat.py:728) | `GET /sabat-ini` | pakai helper `_tenant_ids_for_caller` (keyword tidak di S6-A regex) |
| [`agregat.py::/ytd`](app/api/v1/agregat.py:1019) | `GET /ytd` | sama — pakai helper |
| [`sync.py::/upload`](app/api/v1/sync.py:43) | `POST /upload` | pakai `user: User = Depends(get_current_user)` (DB model dep) |
| [`sync.py::/pull`](app/api/v1/sync.py:78) | `GET /pull` | sama + **REAL SECURITY BUG**: AUDITOR_MISI hanya lihat 1 tenant |

---

## Migrasi yang dilakukan

### Agregat (helper-based pattern)

**Sebelum** (line 759):
```python
@router.get("/sabat-ini", ...)
def agregat_sabat_ini(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ...
    tenant_ids, scope = _tenant_ids_for_caller(db, current_user)
    role = current_user["role"]
```

**Sesudah** (line 728):
```python
@router.get("/sabat-ini", ...)
def agregat_sabat_ini(
    db: Session = Depends(get_db),
    scope: TenantScope = Depends(require_tenant_scope),
):
    ...
    tenant_ids = scope.visible_tenant_ids
    scope_label_map = {
        "BENDAHARA": "tenant", "KETUA_KEUANGAN": "tenant", "PENDETA": "tenant",
        "AUDITOR_MISI": "misi", "ADMIN_UNI": "uni",
    }
    scope_label = scope_label_map.get(scope.role, "unknown")
    role = scope.role
```

Pattern identik untuk `/ytd`.

### Sync (DB-model-dependency pattern)

**`/upload` sebelum**:
```python
def upload_sync(db: Session, user: User = Depends(get_current_user)):
    if user.role not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(403, ...)
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
```

**`/upload` sesudah**:
```python
def upload_sync(db: Session, scope: TenantScope = Depends(require_tenant_scope)):
    if scope.role not in ("BENDAHARA", "KETUA_KEUANGAN"):
        raise HTTPException(403, ...)
    # BENDAHARA/KETUA_KEUANGAN → visible_tenant_ids = [primary_tenant_id]
    tenant_id = scope.primary_tenant_id
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
```

**`/pull` sebelum** (BUG):
```python
def pull_sync(..., user: User = Depends(get_current_user)):
    if user.role not in ("AUDITOR_MISI", "ADMIN_UNI"):
        raise HTTPException(403, ...)
    q = db.query(SyncOutbox).filter(SyncOutbox.pulled_at.is_(None))
    # TIDAK ada filter tenant — return semua outbox dari SEMUA jemaat!
```

**`/pull` sesudah** (FIXED):
```python
def pull_sync(..., scope: TenantScope = Depends(require_tenant_scope)):
    if scope.role not in ("AUDITOR_MISI", "ADMIN_UNI"):
        raise HTTPException(403, ...)
    q = db.query(SyncOutbox).filter(SyncOutbox.pulled_at.is_(None))
    if scope.visible_tenant_ids:
        q = q.filter(SyncOutbox.tenant_id.in_(scope.visible_tenant_ids))
```

---

## Security fix: `sync.py::/pull`

Kode lama **TIDAK filter** `SyncOutbox` by tenant — artinya:
- AUDITOR_MISI menarik SEMUA outbox dari SEMUA jemaat di SEMUA misi
- ADMIN_UNI menarik SEMUA outbox dari SEMUA jemaat di SEMUA uni

Setelah patch:
- AUDITOR_MISI → hanya outbox dari jemaat di misi caller (mengikuti `scope.visible_tenant_ids`)
- ADMIN_UNI → hanya outbox dari jemaat di uni caller

Ini bukan under-coverage bug yang dikhawatirkan sebelumnya — justru over-exposure.
Either way, sekarang sudah ter-filter dengan benar.

> ⚠️ **Catatan:** observasi awal saya di S6-G menyebut "AUDITOR_MISI hanya
> lihat 1 tenant" — itu salah baca. Kode lama `/pull` memang **tidak filter
> sama sekali**. Patch sekarang memberikan scope yang benar.

---

## Helper `_tenant_ids_for_caller` dihapus

Karena `agregat.py::/sabat-ini` dan `/ytd` sekarang pakai `TenantScope`
langsung, helper menjadi orphan. Helper dihapus dan `resolve_tenant_scope`
import juga dihapus dari `agregat.py` (tidak dipakai lagi).

`chart_mingguan` (yang sudah migrasi di S6-B) tidak terpengaruh.

---

## Verifikasi

### Audit script re-run (post-S6-H)

```
File                      Endpoints  Inline  Safe  NoOp  usesTS
agregat.py                      6       0     3     3     YES  ← was 2 inline
sync.py                         2       0     2     0     YES  ← was 2 inline
...
TOTAL                           104      11    25
```

**Both files now clean.** 11 remaining inline adalah false positives
(sudah didokumentasikan di `FASE4_SPRINT6_G_REAUDIT.md`).

### Test suite

```
.venv/bin/python -m pytest tests/ -x --tb=short -q
397 passed, 6 warnings in 132.76s
```

**397/397 tests pass** — tidak ada regresi.

### Files modified

| File | Lines changed |
|---|---|
| [`app/api/v1/agregat.py`](app/api/v1/agregat.py) | -50 helper, +12 inline scope_label, body fixes (4 lokasi) |
| [`app/api/v1/sync.py`](app/api/v1/sync.py) | +import, 2 endpoints rewritten, audit log fix |

---

## Sprint 6 Progress (cumulative)

| Sprint | Status | Commit |
|---|---|---|
| 6-A | ✅ DONE | `fe8d91e` |
| 6-B | ✅ DONE | `7386f25` |
| 6-C | ✅ DONE | `ad34a16` |
| 6-D | ✅ DONE | `ee1273b` |
| 6-E | ✅ DONE | `6eb2ea4` |
| 6-F | ✅ DONE | `e944a31` |
| 6-G | ✅ DONE | `de52d55` |
| **6-H** | **✅ DONE** | **(this sprint)** |
| 6-I | ⏳ Pending | test matrix per role |
| 6-J | ⏳ Pending | cross-tenant leakage test |
| 6-K | ⏳ Pending | coverage verify + summary |

---

## Next: Sprint 6-I (Test matrix per role)

Sprint berikutnya akan bikin test matrix 5 roles × semua migrated endpoints:
- BENDAHARA, KETUA_KEUANGAN, PENDETA (scope: tenant)
- AUDITOR_MISI (scope: misi)
- ADMIN_UNI (scope: uni)

Test memastikan setiap role hanya bisa akses endpoint sesuai scope-nya, dan
return 403 untuk akses endpoint di luar scope.

**Menunggu `LANJUT` untuk mulai S6-I.**