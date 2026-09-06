# FASE 5 — Sprint 3 Summary
## CI Pipeline (ruff + bandit + pip-audit + gitleaks + coverage gate)

**Status:** 🟡 PARTIALLY COMPLETED — Sprint 3 lint/test goals met; **3 blockers remain** (coverage gate, bandit MD5, pip-audit 37 dep vulns).
**Date:** 2026-09-05
**Scope:** GitHub Actions CI (`.github/workflows/ci.yml`), gitleaks secrets scan (`.github/workflows/secrets-scan.yml`), Makefile targets, dependency upgrades (`bandit`, `pip-audit`, `gitleaks` action), badge row in `README.md`, and a comprehensive ruff sweep of `app/` (783 → 0 issues).
**Builds on:** FASE 5 Sprint 1 (structured logging), Sprint 2 (Prometheus metrics).

---

## 1. Goals Recap

S5-3 turns FLIPUS from "lints locally if you remember to run it" into "every push is gated by an auditable CI pipeline":

| Goal | Why it matters |
|------|----------------|
| **ruff zero-findings on `app/`** | Every Ruff rule category the project enables (E/W/F/I/B/C4/S/T20/UP) must be clean, otherwise CI fails. |
| **Bandit security scan** | Catches weak crypto (`B324`), insecure random (`B311`), `assert` statements that disappear under `-O` (`B101`). |
| **pip-audit dependency audit** | Catches known CVEs in pinned deps. Currently runs against the real dep set. |
| **Coverage gate ≥ 69%** | Prevents accidental untested code paths. Configurable via `COVERAGE_MIN` in the workflow. |
| **Gitleaks secrets scan** | Prevents committing `.env`, JWT secrets, PII keys, license salts. |
| **Makefile mirrors CI** | `make ci` reproduces what GitHub Actions runs. |

Without S5-3, regressions (a stray `print()` for debugging, a weak hash, a leaked secret) only get caught in code review — if at all.

---

## 2. Deliverables Checklist

| # | Deliverable | Status | Location |
|---|-------------|--------|----------|
| 1 | `.github/workflows/ci.yml` (lint + typecheck + security + test+coverage, all required for `main`) | ✅ | [`.github/workflows/ci.yml`](.github/workflows/ci.yml:1) |
| 2 | `.github/workflows/secrets-scan.yml` (gitleaks on every push/PR) | ✅ | [`.github/workflows/secrets-scan.yml`](.github/workflows/secrets-scan.yml:1) |
| 3 | `.gitleaks.toml` tuned for FLIPUS (allow `ci-stub-*` secrets) | ✅ | [`.gitleaks.toml`](.gitleaks.toml:1) |
| 4 | `Makefile` targets: `lint`, `lint-fix`, `typecheck`, `security-bandit`, `security-audit`, `security`, `test-cov`, `coverage`, `ci` | ✅ | [`Makefile`](Makefile:1) |
| 5 | `requirements.txt` dev tooling: `bandit==1.7.10`, `pip-audit==2.7.3` | ✅ | [`requirements.txt`](requirements.txt:1) |
| 6 | `README.md` badge row | ✅ | [`README.md`](README.md:1) |
| 7 | `ruff check app/` — **zero findings** | ✅ | this run |
| 8 | `pytest tests/` — **461/461 passing** | ✅ | this run |
| 9 | `bandit -r app/ --skip B105,B106,B107 -ll` | 🟡 **6 findings (2 HIGH)** | §5.1 |
| 10 | `pip-audit --strict --no-deps` | 🟡 **37 vulns in 5 packages** | §5.2 |
| 11 | `pytest --cov=app --cov-fail-under=$COVERAGE_MIN` | 🟡 **52.76% < 69.0% gate** | §5.3 |
| 12 | `actionlint` workflow validation | ✅ (PyYAML