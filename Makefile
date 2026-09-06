# FLIPUS Developer Makefile
# FASE 5 Sprint 3 — CI pipeline targets
# Usage: make <target>

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest
BANDIT := $(VENV)/bin/bandit
PIPAUDIT := $(VENV)/bin/pip-audit

.DEFAULT_GOAL := help

.PHONY: help install test test-fast test-cov lint lint-fix typecheck \
        security-bandit security-audit security coverage coverage-html clean ci

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install dev tooling (mypy, pytest-cov, ruff, bandit, pip-audit)
	$(PIP) install -r requirements.txt

test:  ## Run full test suite
	PYTHONPATH=. $(PYTEST) -q

test-fast:  ## Run tests in parallel, fail fast
	PYTHONPATH=. $(PYTEST) -x -q -n auto 2>/dev/null || PYTHONPATH=. $(PYTEST) -x -q

test-cov:  ## Run tests with coverage report
	PYTHONPATH=. $(PYTEST) --cov=app --cov-report=term-missing -q

coverage:  ## HTML coverage report → htmlcov/index.html
	PYTHONPATH=. $(PYTEST) --cov=app --cov-report=html -q
	@echo "→ Open htmlcov/index.html in your browser"

lint:  ## Run ruff linter (no changes)
	$(RUFF) check app/ tests/

lint-fix:  ## Run ruff linter with auto-fix
	$(RUFF) check --fix app/ tests/

typecheck:  ## Run mypy type checker (warn-only — does not block CI gate)
	@echo "Note: mypy is advisory in CI (continue-on-error: true)."
	-$(MYPY) app/ || true

# ----- FASE 5 Sprint 3: security tooling -----

security-bandit:  ## AST-based security scan (bandit). Skips tests/ scripts/.
	$(BANDIT) -r app/ -ll --skip B105,B106,B107

security-audit:  ## Audit installed deps against PyPI Advisory DB (pip-audit)
	$(PIPAUDIT) --strict \
		--ignore-vuln PYSEC-2026-1325 \
		--ignore-vuln PYSEC-2026-161 \
		--ignore-vuln PYSEC-2026-249 \
		--ignore-vuln PYSEC-2026-248 \
		--ignore-vuln PYSEC-2026-2281 \
		--ignore-vuln PYSEC-2026-2280

security:  ## Run all security checks (bandit + pip-audit)
	$(MAKE) security-bandit
	$(MAKE) security-audit

# Run the same checks GitHub Actions runs, locally.
# Useful as a pre-push check.
ci: lint typecheck security test-cov  ## Run the full CI suite locally
	@echo ""
	@echo "✓ Local CI suite passed."

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
