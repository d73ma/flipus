# FLIPUS Developer Makefile
# FASE 3 Sprint 4 — baseline tooling
# Usage: make <target>

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest

.DEFAULT_GOAL := help

.PHONY: help install test test-fast test-cov lint lint-fix typecheck coverage coverage-html clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install dev tooling (mypy, pytest-cov, ruff)
	$(PIP) install -r requirements.txt
	$(PIP) install mypy==1.13.0 pytest-cov==5.0.0 ruff==0.7.4

test:  ## Run full test suite
	$(PYTEST) -q

test-fast:  ## Run tests in parallel, fail fast
	$(PYTEST) -x -q -n auto 2>/dev/null || $(PYTEST) -x -q

test-cov:  ## Run tests with coverage report
	$(PYTEST) --cov=app --cov-report=term-missing -q

coverage:  ## HTML coverage report → htmlcov/index.html
	$(PYTEST) --cov=app --cov-report=html -q
	@echo "→ Open htmlcov/index.html in your browser"

lint:  ## Run ruff linter (no changes)
	$(RUFF) check app/ tests/

lint-fix:  ## Run ruff linter with auto-fix
	$(RUFF) check --fix app/ tests/

typecheck:  ## Run mypy type checker
	$(MYPY) app/

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
