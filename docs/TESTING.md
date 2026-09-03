# FLIPUS — Testing Guide

> **Version**: 2.1 (FASE 3 Sprint 4 — added §11 Static Type Checking)
> **Scope**: test suite overview, cara run, coverage breakdown, CI integration, mypy
> **Audience**: developer, QA, DevOps
> **Lihat juga**: [`tests/TESTS.md`](../../tests/TESTS.md) untuk coverage matrix historis

---

## 1. Ringkasan

| Statistik | Nilai |
|---|---|
| Total test | **166** |
| Total file test | 10 |
| Framework | pytest 8+ |
| Async | pytest-asyncio |
| Coverage tool | pytest-cov 5.0+ |
| Line coverage (baseline) | **45.3%** (target S4-F: ≥70%) |
| Test DB | SQLite in-memory (`sqlite:///:memory:`) |
| Status | ✅ **166/166 PASS** dalam ~114 detik |

---

## 2. Struktur Test

```
tests/
├── conftest.py                       # fixtures: db, client, auth, users
├── test_accounting_integrity.py      # 29 test — FASE 2 audit (porsi recompute, balance)
├── test_tenant_saas.py               # 21 test — Tahap 20 multi-tenant isolation
├── test_t33_jwt_refresh.py           # 21 test — Tahap 33 JWT + refresh rotation
├── test_t23_approval_2fa.py          # 19 test — Tahap 23 approval workflow + 2FA
├── test_branding.py                  # 18 test — Tahap 21 white-label branding
├── test_t24_notifications.py         # 14 test — Tahap 24 notification center
├── test_t31_logging.py               # 13 test — Tahap 31 structured logging + audit
├── test_t32_cors.py                  # 12 test — Tahap 32 CORS hardening
├── test_t22_search_export.py         # 11 test — Tahap 22 advanced search & export
└── test_t25_e2e.py                   # 8 test  — Tahap 25 end-to-end happy paths
```

**Total per file** (sorted by count):

| # | Test | File | Domain |
|---|---|---:|---|
| 1 | 29 | `test_accounting_integrity.py` | Accounting rules (FASE 2) |
| 2 | 21 | `test_tenant_saas.py` | Multi-tenant isolation |
| 2 | 21 | `test_t33_jwt_refresh.py` | JWT auth + refresh |
| 4 | 19 | `test_t23_approval_2fa.py` | 2FA + approval workflow |
| 5 | 18 | `test_branding.py` | White-label branding |
| 6 | 14 | `test_t24_notifications.py` | Notification system |
| 7 | 13 | `test_t31_logging.py` | Structured logging |
| 8 | 12 | `test_t32_cors.py` | CORS hardening |
| 9 | 11 | `test_t22_search_export.py` | Search + export |
| 10 | 8 | `test_t25_e2e.py` | E2E happy paths |
| | **166** | | |

---

## 3. Cara Menjalankan

### 3.1 Semua Test

```bash
cd /Users/jerrymauri/Flipus

# Aktifkan venv
source .venv/bin/activate

# Run semua
pytest -v

# Atau quiet (CI mode)
pytest -q
```

**Expected output**:
```
........................................................................ [ 43%]
........................................................................ [ 86%]
......................                                                   [100%]
=============================== warnings summary ===============================
... (6 deprecation warnings, all pre-existing)
166 passed, 6 warnings in 114.91s (0:01:54)
```

### 3.2 Test File Tertentu

```bash
# By file
pytest tests/test_accounting_integrity.py -v

# By pattern
pytest -k "tenant" -v
pytest -k "2fa or approval" -v

# By marker (jika sudah ditambahkan)
pytest -m "slow" -v
```

### 3.3 Dengan Coverage Report

```bash
# Terminal report (ringkas)
pytest --cov=app --cov-report=term

# HTML report (detail per file)
pytest --cov=app --cov-report=html
open htmlcov/index.html

# XML report (untuk CI / SonarQube)
pytest --cov=app --cov-report=xml
```

**Atau via Makefile**:
```bash
make test-cov       # terminal report
make coverage       # HTML report
```

### 3.4 Fast Mode (Parallel)

```bash
# Install pytest-xfirst (fail fast)
pip install pytest-xfirst

# Atau manual fail-fast
pytest -x -q

# Parallel execution (perlu pytest-xdist)
pip install pytest-xdist
pytest -n auto -q
```

Lihat [`Makefile`](../../Makefile) untuk target yang sudah dikonfigurasi:
```bash
make test           # full suite
make test-fast      # fail-fast mode
make test-cov       # + coverage
make coverage       # HTML report only
```

---

## 4. Fixtures (conftest.py)

Lihat [`tests/conftest.py`](../../tests/conftest.py).

### 4.1 DB Fixtures

```python
@pytest.fixture
def db():
    """SQLite in-memory DB session, isolated per test."""
    # Setup: create_all, seed master data
    # Yield session
    # Teardown: drop_all
```

### 4.2 HTTP Client

```python
@pytest.fixture
def client(db):
    """FastAPI TestClient bound to in-memory DB."""
    return TestClient(app)
```

### 4.3 Auth Fixtures

```python
@pytest.fixture
def admin_token(client):
    """JWT access token untuk user admin tenant 1."""
    # Login via /api/v1/auth/login, return token string

@pytest.fixture
def bendahara_token(client):
    """JWT access token untuk bendahara."""

@pytest.fixture
def auditor_token(client):
    """JWT access token untuk auditor (cross-tenant read)."""
```

### 4.4 User/Tenant Fixtures

```python
@pytest.fixture
def admin_user(db):
    """User instance dengan role admin, hashed password 'test1234'."""

@pytest.fixture
def tenant(db):
    """Tenant instance dengan branding default."""

@pytest.fixture
def kuitansi(db, admin_user, tenant):
    """Sample kuitansi sabat ini."""
```

---

## 5. Coverage Breakdown (Baseline 45.3%)

Diukur via `pytest --cov=app` per **2026-09-02**:

### 5.1 Modul dengan Coverage Tinggi (>70%)

| Modul | % | Catatan |
|---|---:|---|
| `app/core/security.py` | ~95% | JWT + password hash |
| `app/api/v1/auth.py` | ~90% | Login flow + refresh |
| `app/api/v1/admin.py` | ~85% | Admin endpoints |
| `app/api/v1/tenants.py` | ~85% | Tenant CRUD |
| `app/core/rate_limiter.py` | ~80% | slowapi setup |
| `app/api/v1/notifications.py` | ~78% | Notification CRUD |
| `app/api/v1/twofa.py` | ~75% | 2FA setup/verify |
| `app/api/v1/branding.py` | ~75% | Logo + branding |
| `app/core/upload_validator.py` | ~73% | File validation |

### 5.2 Modul dengan Coverage Sedang (40-70%)

| Modul | % | Catatan |
|---|---:|---|
| `app/api/v1/kuitansi.py` | ~65% | Search + export |
| `app/api/v1/pengeluaran.py` | ~60% | Approval workflow |
| `app/api/v1/dashboard.py` | ~58% | Sabat info |
| `app/services/agregat_service.py` | ~55% | Agregat computation |
| `app/services/porsi_service.py` | ~50% | Porsi recompute |

### 5.3 Modul dengan Coverage Rendah (<40%) — Target S4-F

| Modul | % | Catatan |
|---|---:|---|
| `app/services/whatsapp_service.py` | **0%** | WA integration (butuh mock Fonnte) |
| `app/api/v1/wa_input.py` | ~13% | WA bot inbound |
| `app/services/pdf_gabungan.py` | ~16% | PDF gabungan generator |
| `app/services/backup_service.py` | ~17% | APScheduler backup |
| `app/services/ocr_service.py` | ~25% | Gemini API integration |
| `app/api/v1/pengeluaran_ocr.py` | ~30% | OCR endpoints |
| `app/api/v1/sync.py` | ~35% | Offline sync |
| `app/api/v1/scanner.py` | ~40% | Scanner batch |

**Target S4-F**: naikkan ke ≥70% via penambahan test untuk modul-modul di §5.3.

---

## 6. CI Integration

### 6.1 GitHub Actions (TODO S4-C+6)

Contoh workflow:

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest --cov=app --cov-fail-under=45 --cov-report=xml
      - uses: codecov/codecov-action@v3
```

### 6.2 GitLab CI (TODO S4-C+7)

```yaml
# .gitlab-ci.yml
test:
  image: python:3.12
  script:
    - pip install -r requirements.txt
    - pytest --cov=app --cov-report=xml
  coverage: '/(?i)total.*? (100(?:\.0+)?\%|[1-9]?\d(?:\.\d+)?\%)$/'
```

### 6.3 Pre-commit Hook (Optional)

```bash
pip install pre-commit
cat > .pre-commit-config.yaml <<EOF
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest -q -x
        language: system
        pass_filenames: false
        always_run: true
EOF

pre-commit install
```

---

## 7. Menulis Test Baru

### 7.1 Konvensi

- **File**: `tests/test_<fitur_atau_tahap>.py`
- **Function**: `test_<apa yang diuji>`
- **Class** (opsional): `class Test<Feature>:`
- **Async**: pakai `@pytest.mark.asyncio` decorator + `async def test_...`

### 7.2 Template

```python
"""Test untuk <fitur> — <deskripsi singkat>."""
import pytest
from fastapi.testclient import TestClient


class TestFeatureX:
    """Test suite untuk feature X."""

    def test_create_success(self, client: TestClient, admin_token: str):
        """Test create dengan input valid → 201."""
        resp = client.post(
            "/api/v1/kuitansi/create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "nama_penyetor": "Test User",
                "nominal": 100000,
                "sabat_ke": 1,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["nominal"] == 100000
        assert "id" in data

    def test_create_unauthorized(self, client: TestClient):
        """Test create tanpa token → 401."""
        resp = client.post("/api/v1/kuitansi/create", json={})
        assert resp.status_code == 401

    def test_create_validation_error(self, client: TestClient, admin_token: str):
        """Test create dengan nominal negatif → 422."""
        resp = client.post(
            "/api/v1/kuitansi/create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"nama_penyetor": "X", "nominal": -100, "sabat_ke": 1},
        )
        assert resp.status_code == 422

    @pytest.mark.parametrize("nominal,sabat_ke,expected", [
        (100000, 1, 201),
        (0, 1, 422),       # zero
        (-100, 1, 422),    # negative
        (100000, 53, 422), # invalid sabat
    ])
    def test_create_parametrize(
        self, client: TestClient, admin_token: str,
        nominal: int, sabat_ke: int, expected: int,
    ):
        resp = client.post(
            "/api/v1/kuitansi/create",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"nama_penyetor": "X", "nominal": nominal, "sabat_ke": sabat_ke},
        )
        assert resp.status_code == expected
```

### 7.3 Best Practices

✅ **DO**:
- Satu assertion utama per test (tapi boleh beberapa yang terkait)
- Pakai fixture daripada setup manual
- Test positive + negative + edge case
- Pakai `parametrize` untuk banyak variant input
- Naming yang deskriptif: `test_<apa>_<kondisi>_<ekspektasi>`
- Assert response schema + business rule + side effect

❌ **DON'T**:
- Test terlalu brittle (assertion terhadap timestamp, ID exact)
- Test yang depends pada test lain (state leak)
- Sleep / time-dependent test tanpa freezer
- Mock terlalu banyak sampai test tidak meaningful
- Commit test yang `skip` atau `xfail` permanen tanpa理由

---

## 8. Debugging Test yang Gagal

### 8.1 Lihat Detail Error

```bash
# Short traceback
pytest tests/test_x.py --tb=short

# Long traceback (default)
pytest tests/test_x.py --tb=long

# No traceback (untuk CI, hanya lihat pass/fail)
pytest -q --tb=no
```

### 8.2 Masuk ke PDB saat Gagal

```bash
pytest tests/test_x.py --pdb
# Otomatis drop ke pdb post-mortem saat ada test gagal
```

### 8.3 Print Value

```python
def test_x(client):
    resp = client.get("/api/v1/foo")
    print(f"Response: {resp.json()}")  # muncul di -s mode
    assert resp.status_code == 200
```

```bash
pytest tests/test_x.py -s  # show print output
```

### 8.4 Run Hanya Satu Test

```bash
pytest tests/test_x.py::TestClass::test_method -v
```

---

## 9. Performance & Parallel

### 9.1 Duration Test

```bash
# Lihat test paling lambat
pytest --durations=10

# Fail jika ada test > 5 detik
pytest --durations=10 --strict-markers
```

### 9.2 Parallel Execution

```bash
pip install pytest-xdist
pytest -n 4          # 4 worker processes
pytest -n auto       # sesuai jumlah CPU
```

**Catatan**: parallel execution butuh DB isolation per worker. Saat ini semua test pakai in-memory SQLite, jadi parallel aman.

---

## 10. Referensi

- [`tests/conftest.py`](../../tests/conftest.py) — fixtures definition
- [`tests/TESTS.md`](../../tests/TESTS.md) — coverage matrix historis per tahap
- [`pyproject.toml`](../../pyproject.toml) — `[tool.pytest.ini_options]` config
- [`Makefile`](../../Makefile) — `test`, `test-cov`, `coverage` targets
- [`FASE2_VALIDASI_AKUNTANSI.md`](../../FASE2_VALIDASI_AKUNTANSI.md) — hasil audit accounting integrity
- [`FASE3_AUDIT_BUG_SECURITY.md`](../../FASE3_AUDIT_BUG_SECURITY.md) — bug & security findings
- pytest docs: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- pytest-cov: https://pytest-cov.readthedocs.io/

---

## 11. Static Type Checking (mypy)

> **FASE 3 Sprint 4 — S4-D.R1** mypy pragmas gradual + baseline error suppression.
> **Tujuan**: mengurangi baseline 658 mypy errors → manageable subset untuk ditriage manual, tanpa lose visibility bug nyata.

### 11.1 Baseline (pre-S4-D)

| Metrik | Nilai |
|---|---|
| Errors total | **658** di 39 file |
| Dominated by | `arg-type` 397 + `assignment` 190 (= 587 / 89%) — semua berasal dari SQLAlchemy legacy `Column[T]` vs `T` |
| Real bugs | ~71 (unreachable 6, index 16, union-attr 12, return-value 6, list-item 7, dict-item 6, dll) |
| Mode | non-strict gradual (`disallow_untyped_defs=false`, `disallow_incomplete_defs=false`, `check_untyped_defs=false`) |

### 11.2 Strategi S4-D (hybrid)

| Aksi | Scope | Hasil |
|---|---|---|
| **Inline fix** untuk non-Column[T] errors | Hanya unreachable / index / union-attr / list-item / dict-item / misc / return-value / call-arg / call-overload / operator | ~9 bug nyata diperbaiki (termasuk 2 silent try/except bug di `kuitansi.py:522` dan `m8_managed.py:234`) |
| **Per-module suppress** di `pyproject.toml` | 39 legacy modules punya `Column[T]` pattern; suppress HANYA `arg-type` + `assignment` | 588 error tersembunyi (sesuai desain) |
| **Error code lain TETAP AKTIF** | index, list-item, dict-item, return-value, union-attr, call-arg, call-overload, misc, unreachable, operator | 61 error real bug SURFACE di CI → bisa di-triage manual atau jadi target S4-E |

### 11.3 Hasil (post-S4-D)

| Metrik | Sebelum | Sesudah | Delta |
|---|---|---|---|
| Total errors | 658 | **61** | −90.7% |
| File dengan error | 39 | 19 | −51% |
| Real bug inline-fixed | — | ~9 | +9 |

**61 error yang tersisa** adalah REAL bug dengan tipe:

```
 18 [index]        — list/array indexing pada Optional
  7 [list-item]    — elemen list type mismatch
  6 [dict-item]    — dict key/value mismatch
  5 [unreachable]  — mostly false-positive Column[T] narrowing (S4-E fix)
  5 [union-attr]   — Optional attribute access
  5 [call-arg]     — wrong argument types
  4 [return-value] — wrong return types
  3 [misc]         — bare assignment, etc.
  2 [call-overload]
  2 [unused-ignore]
  1 [operator]
  1 [annotation-unchecked]
```

### 11.4 Bug Nyata Yang Ditemukan & Diperbaiki (S4-D)

1. **`app/utils/number_to_words.py`** — `rupiah_to_words` undefined di `kuitansi.py:522`. Sebelumnya `try/except` diam-diam fallback ke string `"5,000,000 rupiah"` di PDF kuitansi (harusnya `"Lima Juta Rupiah"`). Fixed: tambah alias `rupiah_to_words = bilang = terbilang`.
2. **`app/api/v1/m8_managed.py:234`** — import `fernet` dari `app.core.security` (undefined), tertangkap `try/except` lalu di-print ke stderr. Fixed: hapus bogus import.
3. **`app/api/v1/agregat.py:201`** — `grouped: dict[str, list] = {}` annotation (mypy `[var-annotated]`).
4. **`app/api/v1/agregat.py:836`** — `assert tenant_pct is not None` narrowing (mypy `[union-attr]`).
5. **`app/api/v1/kuitansi.py:340`** — `sort_col: InstrumentedAttribute` hint (mypy `[attr-defined]`). Import dipindah ke top-of-file `if TYPE_CHECKING:` supaya runtime overhead = 0.
6. **`app/api/v1/kuitansi.py:430`** — early return saat `agg is None` sebelum akses `.total/.total_x/.total_pt/.total_khusus` (mypy `[union-attr]` + safety).
7. **`app/api/v1/wa_input.py:507`** — `chosen: Tenant | None` annotation + `assert chosen is not None` (mypy `[union-attr]`).

### 11.5 Cara Menjalankan

```bash
# Baseline — strict, exit 1 jika error > 0
make typecheck                      # atau: .venv/bin/python3 -m mypy app

# Statistik saja
.venv/bin/python3 -m mypy app 2>&1 | tail -3

# Detail breakdown per error code
.venv/bin/python3 -m mypy app 2>&1 | grep -oE " \[[a-z-]+\]$" | sort | uniq -c | sort -rn
```

### 11.6 Konfigurasi (`pyproject.toml` [tool.mypy])

- **Mode**: gradual (`disallow_untyped_defs=false`, `disallow_incomplete_defs=false`, `check_untyped_defs=false`)
- **Strict saja**: `strict_optional=true`, `warn_unused_ignores=true`, `warn_redundant_casts=true`, `warn_unreachable=true`
- **Exclude**: `.venv`, `.venv.broken314`, `frontend`, `scripts/migrate_`, `storage`, `tests/`, `docs/`
- **Per-module suppress**: 39 legacy file dengan `disable_error_code = ["arg-type", "assignment"]`. Error code lain TIDAK di-suppress supaya bug nyata tetap muncul.

### 11.7 Roadmap

| Sprint | Tujuan | Target |
|---|---|---|
| **S4-D** ✅ DONE | Baseline + selective suppression | 658 → 61 errors |
| **S4-E** | Migrate `Column[T]` → `Mapped[T]` (1 model template) + apply ke 1-2 modules | Lepas suppress untuk migrated modules |
| **S5+** | Lanjutkan migrasi incremental | Target akhir: 0 mypy errors (strict optional) |

### 11.8 Notes Penting

- **Jangan menambah file ke daftar suppress tanpa diskusi** — jika kamu butuh menulis module baru yang pakai SQLAlchemy legacy, gunakan `Mapped[T]` style (SQLAlchemy 2.0) supaya langsung bersih.
- **Jangan disable error code lain** di luar `arg-type` + `assignment` — itu penuh dengan info real bug.
- **CI integration**: tambahkan `mypy app` ke CI pipeline sebelum Sprint 5 ditutup (lihat §6).

### 11.9 Referensi

- [`pyproject.toml`](../../pyproject.toml) — `[tool.mypy]` + `[[tool.mypy.overrides]]`
- [mypy docs](https://mypy.readthedocs.io/)
- [SQLAlchemy 2.0 Mapped[T] migration guide](https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html)
- [`FASE3_AUDIT_BUG_SECURITY.md`](../../FASE3_AUDIT_BUG_SECURITY.md) — Sprint 4 plan
