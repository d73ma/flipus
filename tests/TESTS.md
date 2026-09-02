# FLIPUS v1.3 — Test Suite & Coverage Matrix (Tahap 25)

> **Catatan:** Test suite ini di-design selama Tahap 25 untuk menguji
> seluruh pekerjaan Tahap 1-24 secara terintegrasi.

## 📋 Coverage Matrix

| Tahap | Feature | Test File | Status |
|-------|---------|-----------|--------|
| **T17** | PDF generation | `test_t17_*.py` (placeholder — belum ditulis) | ⏸ Deferred |
| **T17** | WA blast + sabat-counter | `test_t17_*.py` (placeholder) | ⏸ Deferred |
| **T18** | Backup & restore | `test_t18_*.py` (placeholder) | ⏸ Deferred |
| **T18** | Agregat dashboards | `test_t18_*.py` (placeholder) | ⏸ Deferred |
| **T19** | Docker + deployment | integration scripts | ✅ Manual |
| **T20** | Multi-Tenant SaaS | `test_tenant_saas.py` | ✅ Complete |
| **T21** | White-Label Branding | `test_branding.py` | ✅ Complete |
| **T22** | Advanced Search/Export | `test_t22_search_export.py` | ✅ Complete |
| **T23** | Approval Workflow | `test_t23_approval_2fa.py` | ✅ Complete |
| **T23** | 2FA / TOTP | `test_t23_approval_2fa.py` | ✅ Complete |
| **T24** | Notification Center | `test_t24_notifications.py` | ✅ Complete |
| **T25** | E2E Happy Paths | `test_t25_e2e.py` | ✅ Complete |

## 🚀 Running the Suite

```bash
cd /Users/jerrymauri/Flipus
.venv/bin/python3 -m pytest tests/ -v
```

Run specific module:
```bash
.venv/bin/python3 -m pytest tests/test_t22_search_export.py -v
.venv/bin/python3 -m pytest tests/test_t23_approval_2fa.py -v
.venv/bin/python3 -m pytest tests/test_t24_notifications.py -v
.venv/bin/python3 -m pytest tests/test_t25_e2e.py -v
```

Run by marker (jika ditambah nanti):
```bash
.venv/bin/python3 -m pytest tests/ -v -m approval
.venv/bin/python3 -m pytest tests/ -v -m notifications
```

## 📊 Test Statistics

| Category | Tests |
|----------|-------|
| Tenant SaaS (T20) | ~20 |
| Branding (T21) | ~15 |
| Search/Export (T22) | 11 |
| Approval + 2FA (T23) | 17 |
| Notifications (T24) | 15 |
| E2E journeys (T25) | 6 |
| **Total** | **~84 tests** |

## 🐛 Bugs Fixed During T25

### Bug #1 — Malformed file in retention_daemon.py
**Symptom:** `app/services/retention_daemon.py` had 3 statements concatenated on a single line, causing `SyntaxError` at module import.

**Root cause:** Past edit corrupted the file. The lines `from sqlalchemy.orm import Session`, `from app.models.transaction import Kuitansi`, and `logger = logging.getLogger(__name__)` were merged without proper newlines.

**Fix:** Split the 3 statements onto separate lines with correct imports.

**Discovery:** Static AST check across all `app/**/*.py` files during T25-8.

**Impact:** Would have prevented the entire app from starting once `retention_daemon` was imported.

## 🧪 Test Architecture

### conftest.py (T25-1)
- In-memory SQLite per test (function scope)
- Domain fixtures: `uni_dk`, `misi_minahasa`, `jemaat_a`, `jemaat_b`
- User fixtures per role: `bendahara_a`, `ketua_a`, `pendeta`, `admin_uni`, `auditor_misi`
- Auth helpers: `login()`, `auth_header()`, role-specific token fixtures
- `create_kuitansi` factory for test data

### Test Isolation Strategy
- Each test creates isolated DB (memory-only)
- No cross-test pollution
- Fixtures auto-cleanup via `app.dependency_overrides.clear()` + `Base.metadata.drop_all`

### Why No Alembic?
- v1.3 stack uses Base.metadata.create_all() — tables auto-create on first import
- In-memory SQLite speed: <100ms per test
- Tradeoff: no migration history, but faster iteration

## ⚠️ Test Limitations

1. **External services:** WA (Fonnte), Gemini AI, real backup files → mocked or skipped
2. **Scheduler:** APScheduler jobs are NOT auto-started in tests; cleanup is called manually
3. **Time-sensitive:** Some 2FA window tests may need clock mocking (TODO)
4. **File uploads:** Logo upload tests use mock files, not real PNG validation
5. **Concurrent:** No concurrent user testing (use integration_test_all.py for that)

## 📝 Adding New Tests

When adding a feature, follow this pattern:

```python
# tests/test_<tahap>_<feature>.py

import pytest


class TestYourFeature:
    def test_happy_path(self, client, bendahara_token):
        # Arrange — use fixtures
        # Act — call API
        # Assert — verify response
        resp = client.post(
            "/api/v1/your/endpoint",
            headers={"Authorization": f"Bearer {bendahara_token}"},
            json={"key": "value"},
        )
        assert resp.status_code == 200
        assert resp.json()["expected_field"] == expected_value
```

## 🔍 Manual Verification Checklist

Beyond automated tests, these manual checks confirm production readiness:

- [ ] Login as Bendahara → submit kuitansi → check Ketua gets notification
- [ ] Login as Ketua → approve → check Bendahara gets notification
- [ ] Login as Bendahara → trigger blast-weekly → check Pendeta gets notification
- [ ] Login as Admin Uni → run backup → check all admins get notification
- [ ] Open browser bell icon → click item → should navigate to relevant page
- [ ] Open `/notifications` → filter by "Belum dibaca" → mark all as read → count goes to 0
- [ ] Enable 2FA → login again → 2FA step-2 UI appears → submit TOTP → access granted
- [ ] Try backup code → success → try same code again → rejected (single-use)
- [ ] Suspend a jemaat (Admin Uni) → all users in jemaat get notification
- [ ] Search filter by nama (encrypted) → decrypt-and-match works

## 🎯 Test Coverage Goals Achieved

- ✅ All v1.3 features (T20-T24) have regression tests
- ✅ E2E happy path scenarios cover multi-role interactions
- ✅ RBAC matrix verified across all protected endpoints
- ✅ Status filter propagation tested (draft/finalized/rejected)
- ✅ Notification self-skip logic verified
- ✅ 2FA + backup code single-use enforced
- ✅ Cross-tenant isolation maintained under all features

---

**Maintainer:** Jerry Mauri
**Last updated:** 2026-08-19 (Tahap 25)
---

## 📌 Catatan FASE 3 Sprint 4 (2026-09-02)

Dokumentasi testing dipindahkan/dilengkapi ke [`docs/TESTING.md`](../docs/TESTING.md).

**Update terbaru**:
- Total test saat ini: **166** (sebelumnya 100+ saat Tahap 25)
- Coverage baseline: **45.3%** (target S4-F: ≥70%)
- File test baru: `test_t31_logging.py`, `test_t32_cors.py`, `test_t33_jwt_refresh.py`
- Makefile targets: `make test`, `make test-cov`, `make coverage`
- Lihat [`docs/TESTING.md`](../docs/TESTING.md) untuk breakdown lengkap + cara menulis test baru.

