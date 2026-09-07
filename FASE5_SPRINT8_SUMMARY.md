# FASE 5 — Sprint 8 Summary
## Coverage Finish (cross 67%) + QuickInput Bug Fix → v2.5.0

**Status:** ✅ COMPLETED — 797/797 tests passing, 70.1% coverage (gate 67%), 0 bandit, 0 pip-audit.
**Date:** 2026-09-07
**Branch:** `sprint8/coverage-finish` (1 commit since v2.4.0)
**Builds on:** FASE 5 Sprint 7 (v2.4.0)

**FASE 5 SELESAI.** Coverage target 67% terlampaui (70.1%). Ini adalah sprint
terakhir dari Fase 5 (operational hardening).

---

## 1. Goals Recap

Sprint 7 reached 66.7% (gate 66%). Sprint 8 crosses the 67% target by covering the
remaining untested modules and fixes a critical bug found along the way.

**Achieved: 70.1% coverage** (target 67% met + 3.1pp buffer).

---

## 2. Deliverables Checklist

| # | Deliverable | Status | Coverage lift |
|---|-------------|--------|---------------|
| 1 | `quick_input.py` POST quick-input | ✅ 14 tests | 35.1% → 91.9% |
| 2 | `m8_managed.py` invite + void | ✅ 22 tests | 28.7% → 70.7% |
| 3 | `cloud_parser.py` Gemini OCR | ✅ (in ai_engine) | 13.9% → 79.2% |
| 4 | `batch_processor.py` batch OCR | ✅ (in ai_engine) | 12.3% → 93.0% |
| 5 | Fix quick_input `.first()` bug | ✅ | — |
| 6 | Raise COVERAGE_MIN 66.0 → 67.0 | ✅ | — |
| 7 | Summary + CHANGELOG v2.5.0 | ✅ | — |

**Total: +52 tests (745 → 797), coverage 66.7% → 70.1% (+3.4pp).**

---

## 3. BUG FIX — quick_input `.first()` comment-swallowed

### Root cause

`app/api/v1/quick_input.py:232`:
```python
tenant = db.query(Tenant).filter(...)  # noqa: E712.  .first()
```

The `.first()` was inside the `# noqa` comment, so it was never executed. `tenant`
became a `Query` object instead of a `Tenant` → `AttributeError: 'Query' object has
no attribute 'id'` on **every** `POST /kuitansi/quick-input` call.

### Fix

Moved `.first()` out of the comment and reformatted the chain:
```python
tenant = (
    db.query(Tenant)
    .filter(Tenant.id == tenant_id, Tenant.is_active == True)  # noqa: E712
    .first()
)
```

### Impact

The v2.0 M1 PWA Quick Input endpoint was silently broken — no test exercised it.
This is the third critical bug surfaced by the coverage-lift effort (after AWAIT_NAMA
and number_to_words miliar crash), confirming the value of the test-first approach.

---

## 4. Coverage Lift (FASE 5 complete picture)

| Module | Sprint 8 lift | Final |
|--------|---------------|-------|
| `app/api/v1/quick_input.py` | +56.8pp | 91.9% |
| `app/api/v1/m8_managed.py` | +42.0pp | 70.7% |
| `app/ai_engine/cloud_parser.py` | +65.3pp | 79.2% |
| `app/ai_engine/batch_processor.py` | +80.7pp | 93.0% |

**Total FASE 5 coverage progression (Kilo sprints):**
- Sprint 4: 52.76% → 53.5%
- Sprint 5: 53.5% → 61.1%
- Sprint 6: 61.1% → 61.8%
- Sprint 7: 61.8% → 66.7%
- Sprint 8: 66.7% → **70.1%**

---

## 5. Test Files Added (Sprint 8)

- `tests/test_s8_s8f_quick_input.py` — 14 tests
- `tests/test_s8_s8f_m8_managed.py` — 22 tests
- `tests/test_s8_s8f_ai_engine.py` — 16 tests

---

## 6. Verification — Local `make ci` PASSED

```bash
$ make ci
ruff check                            → All checks passed!
bandit -ll                            → 0 HIGH, 0 MEDIUM, 0 LOW
pip-audit --strict                    → No known vulnerabilities found
pytest --cov-fail-under=67            → 797 passed, 70.1% coverage
```

**Result**: ✅ Local CI suite passed.

---

## 7. FASE 5 — Retrospective

FASE 5 (operational hardening) complete across 5 Kilo sprints (S4–S8):

| Deliverable | Status |
|-------------|--------|
| CI pipeline (bandit + pip-audit + coverage gate) | ✅ |
| Security: bandit 0 HIGH, pip-audit 0 vulns (0 suppress) | ✅ |
| Coverage gate: 47% → 67% enforced | ✅ 70.1% |
| Alembic baseline migration | ✅ |
| PyJWT migration (abandoned python-jose) | ✅ |
| Pydantic v2 Config migration | ✅ |
| Repo hygiene + GitHub release pipeline | ✅ v2.2.0 → v2.5.0 |
| 3 critical bugs fixed (AWAIT_NAMA, number_to_words, quick_input) | ✅ |

**Remaining FASE 5 debt (deferred to FASE 6+):**
- mypy 76 errors (advisory, continue-on-error)
- `pengeluaran_wa.py` (12.9%) — mirrors wa_input, lowest remaining coverage
- `scanner.py` (36.9%), `admin.py` (40.3%), `reports.py` (43%) — medium coverage

---

## 8. Sign-off

Sprint 8 complete. **FASE 5 SELESAI.**

- ✅ 52 tests, coverage 66.7% → 70.1% (crossed 67% target)
- ✅ QuickInput `.first()` bug fixed
- ✅ COVERAGE_MIN raised to 67.0%

**Next: production deployment** (live URL) — see Sprint 8.6 / Jerry's next instruction.

Status: **READY for deployment + FASE 6** — menanti Jerry's go-ahead.