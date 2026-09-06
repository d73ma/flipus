# FASE 4 — Sprint 5 Summary

## Tujuan

Membangun **fondasi terpusat** untuk tenant visibility agar semua endpoint FLIPUS
memiliki *single source of truth* untuk menentukan jemaat mana saja yang boleh
dilihat oleh user. Sebelumnya, logika ini tersebar (duplicated) di banyak modul
(`kuitansi.py`, `agregat.py`) — risiko inkonsistensi & bug cross-tenant bocor.

## Deliverables

| Step | Commit | Deskripsi |
|------|--------|-----------|
| S5-A | `169924b` | Create [`app/core/tenant_scope.py`](../Flipus/app/core/tenant_scope.py) — modul sentral |
| S5-B | `15734b6` | Migrate [`kuitansi.py`](../Flipus/app/api/v1/kuitansi.py) (4 endpoints) |
| S5-C | `c91f1dd` | Migrate [`agregat.py`](../Flipus/app/api/v1/agregat.py) (`_tenant_ids_for_caller` jadi thin wrapper) |
| S5-D | `eea8738` | 30 unit tests untuk [`tenant_scope.py`](../Flipus/app/core/tenant_scope.py) |
| S5-E | (this commit) | Full regression suite — 397/397 passed, no regression |

## Apa yang dihasilkan [`app/core/tenant_scope.py`](../Flipus/app/core/tenant_scope.py)

Modul 271 baris berisi:

### 1. Konstanta RBAC (single source of truth)

```python
ROLE_JEMAAT_ONLY = {"BENDAHARA", "KETUA_KEUANGAN", "PENDETA"}
ROLE_AUDITOR_MISI = "AUDITOR_MISI"
ROLE_ADMIN_UNI = "ADMIN_UNI"
ALL_ROLES = ROLE_JEMAAT_ONLY | {ROLE_AUDITOR_MISI, ROLE_ADMIN_UNI}
```

### 2. `TenantScope` (frozen dataclass)

Immutable value object:

```python
@dataclass(frozen=True)
class TenantScope:
    role: str
    primary_tenant_id: Optional[int]
    visible_tenant_ids: List[int]
    user_id: Optional[int]
    is_cross_tenant: bool

    def can_see(self, tenant_id: int) -> bool: ...
    def __contains__(self, tenant_id: int) -> bool: ...
```

### 3. `resolve_tenant_scope(db, current) → TenantScope`

Pure function. Logika:

| Role | visible_tenant_ids | is_cross_tenant |
|------|--------------------|-----------------|
| BENDAHARA / KETUA_KEUANGAN / PENDETA | `[caller.tenant_id]` | `False` |
| AUDITOR_MISI | semua jemaat di `caller.tenant.misi_konferens_id` | `True` |
| ADMIN_UNI | semua jemaat via chain uni → misi → jemaat | `True` |
| Unknown role | `ValueError` | — |

Boundary cases:
- Primary tenant deleted → return scope dengan `visible_tenant_ids=[]`
- `tenant_id=None` di JWT → return scope dengan `visible_tenant_ids=[]`
- Orphan tenant (`misi_konferens_id=NULL`) untuk AUDITOR_MISI → `visible_tenant_ids=[]`
- ADMIN_UNI dengan Uni tanpa Misi → `visible_tenant_ids=[]`

### 4. `require_tenant_scope` (FastAPI Depends)

```python
def require_tenant_scope(
    db: Session = Depends(get_db),
    current: dict = Depends(get_current_user),
) -> TenantScope:
    scope = resolve_tenant_scope(db, current)
    if not scope.visible_tenant_ids:
        raise HTTPException(403, "...")
    return scope
```

Dipakai di endpoint seperti:
```python
@router.get("/search")
async def search_kuitansi(
    scope: TenantScope = Depends(require_tenant_scope),
    ...
):
    query = query.filter(Kuitansi.tenant_id.in_(scope.visible_tenant_ids))
```

### 5. `tenant_filter(query, model, scope)`

SQLAlchemy helper — apply `IN` clause:

```python
def tenant_filter(query, model, scope):
    if not hasattr(model, "tenant_id"):
        raise AttributeError(f"{model.__name__} has no tenant_id column")
    return query.filter(model.tenant_id.in_(scope.visible_tenant_ids))
```

### 6. `assert_can_access(scope, tenant_id)`

Defense-in-depth untuk service layer. Raise 403 jika di luar scope.

## Migrasi Endpoint

### [`kuitansi.py`](../Flipus/app/api/v1/kuitansi.py) (S5-B)

4 endpoint dimigrasi: `/search`, `/filter-meta`, `/export`, `/{kuitansi_id}/pdf`.
Inline `_get_visible_tenant_ids` (28 baris) dihapus. **Net: +22/-36 baris.**

### [`agregat.py`](../Flipus/app/api/v1/agregat.py) (S5-C)

`_tenant_ids_for_caller` (line 720) yang duplikat tenant resolution logic
diubah jadi **thin wrapper** di atas `resolve_tenant_scope`. Signature
`(ids, label)` dipertahankan untuk backward-compat dengan 3 call sites.

**Net: +34/-20 baris.** Full test suite 367 → 367 passed.

### Dideferred untuk Sprint 6 (FASE4-S6)

- Inline role-check di `/sabat-ini` endpoint (agregat.py:269)
- Inline role-check di `/chart` endpoint (agregat.py:1212) — ini **third duplicate**
- Migrasi modul lain: notifications, scanner, quick_input, pengeluaran, users,
  master, reports, dashboard, wa_input

Catatan: endpoint-endpoint di atas sudah punya explicit role guard
(`if current_user["role"] != "ADMIN_UNI": raise 403`), jadi tidak vulnerable —
tapi duplikasi code sebaiknya dihilangkan untuk konsistensi.

## Test Coverage

[`tests/test_tenant_scope.py`](../Flipus/tests/test_tenant_scope.py) — 589 baris, 30 tests:

| Class | Tests | Fokus |
|-------|-------|-------|
| `TestTenantScopeDataclass` | 7 | `can_see`, `__contains__`, frozen semantics, `is_cross_tenant` flag |
| `TestResolveHappyPaths` | 5 | 5 RBAC roles — happy path |
| `TestResolveBoundaryCases` | 6 | Orphan, unknown role, missing FK, legacy tenant |
| `TestCrossTenantLeakage` | 2 | **CRITICAL**: ADMIN_UNI tidak lihat jemaat uni lain; AUDITOR_MISI tidak lihat jemaat misi lain |
| `TestTenantFilterHelper` | 2 | `in_()` filter applied + `AttributeError` untuk model tanpa `tenant_id` |
| `TestAssertCanAccess` | 2 | No-raise untuk visible, 403 untuk out-of-scope |
| `TestRequireTenantScopeDependency` | 2 | Integration via FastAPI Depends |
| `TestRoleConstants` | 4 | Sanity checks pada role constants |

**Total: 30/30 passed in 2.07s.**

### Bug yang ditemukan saat test writing

- `test_admin_uni_with_uni_having_no_misi_returns_empty_scope` awalnya return `[1]`
  karena reused `jemaat_a` punya stale `nama_uni`. Fix: bikin tenant fresh dengan
  Uni "Uni Empty NoMisi" tanpa misi.
- `test_returns_scope_when_visible_non_empty` awalnya 401 pada BENDAHARA login
  karena signature fixture tidak minta `bendahara_a` — user BENDAHARA tidak
  dibuat di DB. Fix: tambah `bendahara_a` ke parameter list.

## Regression Test (S5-E)

```
397 passed, 6 warnings in 132.08s
```

- Sebelum Sprint 5: 367 tests
- Setelah Sprint 5: 397 tests (+30 dari S5-D)
- **Tidak ada regresi**: semua test lama tetap lulus.

## Catatan Keamanan

1. **Single source of truth**: Logika tenant visibility sekarang hanya ada di
   satu tempat. Jika ada perubahan RBAC atau struktur organisasi (misal tambah
   role baru), cukup edit satu file.

2. **Defense-in-depth**: `assert_can_access` bisa dipakai di service layer
   sebagai pengaman tambahan. Contoh:
   ```python
   def get_kuitansi(scope: TenantScope, kuitansi_id: int):
       kuitansi = db.query(Kuitansi).filter_by(id=kuitansi_id).first()
       assert_can_access(scope, kuitansi.tenant_id)  # raise jika out of scope
       return kuitansi
   ```

3. **Fail-closed**: Orphan tenant / missing FK → `visible_tenant_ids=[]` → 403.
   Lebih aman daripada fail-open (return all).

4. **Cross-tenant leakage test** ada di test suite — guard otomatis agar tidak
   regresi.

## Sprint Berikutnya

**Sprint 6: Audit & Patch Semua Endpoint** — 6-A audit script, 6-B sampai 6-G
patch semua endpoint yang masih pakai inline tenant logic (notifications,
scanner, quick_input, pengeluaran, users, master, reports, dashboard, wa_input).
Plus 6-H test matrix per role, 6-I cross-tenant leakage test per endpoint,
6-J coverage verify.

## Files Changed di Sprint 5

- Created: [`app/core/tenant_scope.py`](../Flipus/app/core/tenant_scope.py) (271 baris)
- Created: [`tests/test_tenant_scope.py`](../Flipus/tests/test_tenant_scope.py) (589 baris)
- Modified: [`app/api/v1/kuitansi.py`](../Flipus/app/api/v1/kuitansi.py) (+22/-36)
- Modified: [`app/api/v1/agregat.py`](../Flipus/app/api/v1/agregat.py) (+34/-20)

**Total: 4 files, +916/-56 baris.**