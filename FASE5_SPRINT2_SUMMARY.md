# FASE 5 — Sprint 2 Summary
## Prometheus Metrics + /metrics Endpoint + Grafana Dashboard

**Status:** ✅ COMPLETED (16/16 tests passing, registry mismatch bug fixed, all 4 custom metrics wired)
**Date:** 2026-09-03
**Scope:** 4 custom `flipus_*` metrics + HTTP auto-metrics via `prometheus-fastapi-instrumentator` + `/metrics` scrape endpoint + Grafana dashboard JSON template.
**Builds on:** FASE 5 Sprint 1 (Structured Logging — service identity + security hook + `log_security_event()`).

---

## 1. Goals Recap

S5-2 turns FLIPUS from "we have logs" to "we have logs + a Prometheus-scrapeable metrics surface that lets Grafana answer:

- Are HTTP requests healthy? (p50/p95/p99 latency, 5xx rate, request rate by status)
- Is the WA blast actually delivering? (success/failed/skipped by target_role)
- Is the business healthy? (kuitansi creation rate by source)
- Is the AI stack healthy? (gemini vs ollama latency + outcome breakdown)
- Is anyone trying to break in? (security events by event_type)"
"

Without S5-2, S5-1 logs are the only production observability we have. With S5-2 we get quantitative SLO tracking + alerting capability (alert rules land in S5-8 along with the disaster-recovery runbook).

---

## 2. Deliverables Checklist

| # | Deliverable | Status | Location |
|---|-------------|--------|----------|
| 1 | 4 custom `flipus_*` Prometheus metrics defined | ✅ | [`app/core/metrics.py`](app/core/metrics.py:67) |
| 2 | Public helper API: `record_*()` + `observe_ai_inference()` context manager | ✅ | [`app/core/metrics.py`](app/core/metrics.py:146) |
| 3 | `BUILD_INFO` gauge carrying service+version labels | ✅ | [`app/core/metrics.py`](app/core/metrics.py:127) |
| 4 | `record_wa_blast()` wired into [`app/services/whatsapp.py`](app/services/whatsapp.py) (3 send functions × 4 return points) | ✅ | helper at top of file |
| 5 | `record_kuitansi_created()` wired into scanner, quick_input, pengeluaran_ocr | ✅ | 3 endpoints |
| 6 | `observe_ai_inference()` wrapping `extract_with_ollama` + `validate_with_gemini` | ✅ | local_ocr + cloud_parser |
| 7 | `/metrics` endpoint exposed via `prometheus-fastapi-instrumentator` | ✅ | [`app/main.py`](app/main.py:226) |
| 8 | **Registry mismatch bug FIXED** (custom `REGISTRY` passed to `Instrumentator`) | ✅ | [`app/main.py`](app/main.py:235) |
| 9 | Test suite: 16 tests covering unit + integration | ✅ | [`tests/test_t32_metrics.py`](tests/test_t32_metrics.py) |
| 10 | Grafana dashboard JSON template | ✅ | [`ops/grafana/flipus-dashboard.json`](ops/grafana/flipus-dashboard.json) |
| 11 | This summary doc | ✅ | `FASE5_SPRINT2_SUMMARY.md` |

---

## 3. The 4 Custom Metrics

| Metric | Type | Labels | Emitted by |
|--------|------|--------|-----------|
| `flipus_security_events_total` | Counter | `event`, `outcome` | [`record_security_event()`](app/core/metrics.py:146) — called by [`log_security_event()`](app/core/logger.py) hook from S5-1 |
| `flipus_wa_blast_total` | Counter | `target_role`, `outcome` | [`record_wa_blast()`](app/core/metrics.py:155) — called from [`app/services/whatsapp.py`](app/services/whatsapp.py) after each send attempt |
| `flipus_kuitansi_created_total` | Counter | `source`, `outcome` | [`record_kuitansi_created()`](app/core/metrics.py:165) — called from scanner.py, quick_input.py, pengeluaran_ocr.py after `db.commit()` |
| `flipus_ai_inference_seconds` | Histogram | `provider`, `model`, `outcome` | [`observe_ai_inference()`](app/core/metrics.py:176) context manager — wraps ollama + gemini calls |
| `flipus_build_info` | Gauge (always=1) | `service`, `version` | set once at module import, label values = `SERVICE_NAME` + `SERVICE_VERSION` |

### 3.1 Why these 4?

1. **Security events** — already emitted as structured logs by S5-1. Counting them in metrics gives us rate-based alerting ("alert if `outcome=forbidden` > 10/min") without re-implementing the log-parsing pipeline.

2. **WA blast** — Fonnte is the only outbound integration in the system that can fail silently. A spike in `outcome=failed` for `target_role=majelis` is an actionable signal.

3. **Kuitansi created** — the single most important business KPI. Track by `source` to know whether users are scanning ampop, using quick-input, or OCR-ing scans. Counts both `ok` and `failed` outcomes so we can compute success-rate without joining.

4. **AI inference latency** — two providers (gemini cloud + ollama local). We need to know whether Gemini is degrading before complaints roll in, and whether the Ollama fallback is being used.

5. **`flipus_build_info`** — always=1 Gauge with service+version labels is the idiomatic Prometheus way to attach build identity to every scrape. Lets Grafana dashboards show "which build is this?" without a separate discovery job.

### 3.2 Cardinality budget

| Metric | Label combinations | Cardinality |
|--------|-------------------|-------------|
| `flipus_security_events_total` | `event` (~12 distinct: `login_ok`, `login_failed`, `forbidden`, `password_reset_requested`, ...) × `outcome` (`ok`/`failed`/`blocked`) | ~36 |
| `flipus_wa_blast_total` | `target_role` (BENDAHARA, PENDETA, KETUA_KEUANGAN, blast, unknown) × `outcome` (sent/failed/skipped/timeout) | ~20 |
| `flipus_kuitansi_created_total` | `source` (scanner, quick_input, ocr, manual, api) × `outcome` (ok/failed) | ~10 |
| `flipus_ai_inference_seconds` | `provider` (gemini, ollama_local) × `model` (~4 distinct) × `outcome` (ok/parse_fail/suspicious/error) | ~24 |

Total bounded <100 series — well under Prometheus's 10k+ comfort zone for a single-tenant app.

---

## 4. The Registry Mismatch Bug (and Fix)

### What happened

First verification of `/metrics` returned HTTP 200 with `flipus_* lines: 0`. Custom metrics were being incremented in the process but did NOT appear in the scrape output. Two hours of "is this a permissions issue? is the counter even being created?" debugging led to root cause:

**`prometheus-fastapi-instrumentator`'s `Instrumentator.expose()` uses its own `self.registry` to render the scrape** (verified in [library source](https://github.com/trallnag/prometheus-fastapi-instrumentator/blob/master/src/prometheus_fastapi_instrumentator/instrumentation.py)). Default is `prometheus_client.REGISTRY` (the global default). But [`app/core/metrics.py`](app/core/metrics.py:67) registers the 4 custom metrics on a **separate** `CollectorRegistry(auto_describe=True)`. Result: two disjoint registries, two disjoint scrape surfaces, one `/metrics` endpoint only rendering the default registry.

### Why we kept the custom registry (instead of just moving to default)

The custom `CollectorRegistry` gives us:
- **Isolation from third-party noise**: any library that auto-registers on `prometheus_client.REGISTRY` (e.g., `multiprocess` collector, stray `apscheduler` metric) is excluded from our scrape.
- **Clean `generate_latest()` output**: predictable line ordering, no orphaned series.
- **Testability**: tests can assert against OUR specific metrics without grepping through the entire prometheus_client default registry.

### The fix

Two-line fix in [`app/main.py`](app/main.py:232):

```python
from app.core.metrics import REGISTRY as _flipus_metrics_registry
Instrumentator(
    ...,
    registry=_flipus_metrics_registry,  # ← THE FIX
).instrument(app).expose(...)
```

`prometheus-fastapi-instrumentator` constructor accepts a `registry: CollectorRegistry` kwarg (verified in [`instrumentation.py:104-107`](https://github.com/trallnag/prometheus-fastapi-instrumentator/blob/master/src/prometheus_fastapi_instrumentator/instrumentation.py)). Setting it to our custom `REGISTRY` makes the Instrumentator's HTTP metrics (http_request_duration_highr_seconds_*, http_requests_inprogress) write into OUR registry, alongside the 4 custom `flipus_*` metrics. One registry, one `/metrics` scrape.

### Verification

```text
STATUS 200
LEN 6695
flipus_* lines: 31
http_* lines: 25
  OK  flipus_security_events_total{event="t52_healthcheck",outcome="ok"} 1.0
  OK  flipus_kuitansi_created_total{outcome="ok",source="t52_verify"} 1.0
  OK  flipus_ai_inference_seconds_bucket{...outcome="ok",provider="gemini"} 1.0
  OK  flipus_build_info{service="flipus",version="1.5.0"} 1.0
VERIFICATION_OK: /metrics exposes both flipus_* and http_* families
```

---

## 5. Wiring Map

Where each helper is called from production code (not test code):

| Helper | Caller | Purpose |
|--------|--------|---------|
| `record_security_event(event, outcome)` | [`app/core/logger.py:log_security_event()`](app/core/logger.py) (auto, via S5-1 hook) | Centralised via logger — call sites use `log_security_event()`, metrics get bumped for free. |
| `record_wa_blast(target_role, outcome)` | [`app/services/whatsapp.py:_record_wa_blast_metric()`](app/services/whatsapp.py) helper at top of file | 3 send functions × 4 return points (success, error, exception, exhausted retries). `target_role` defaults: "majelis", "general", "blast" (per-function). |
| `record_kuitansi_created(source, outcome)` | [`app/api/v1/scanner.py:/scanner/save-batch`](app/api/v1/scanner.py) | Loops `len(saved_items)` times → `source="scanner_batch"` |
| | [`app/api/v1/quick_input.py:/kuitansi/quick-input`](app/api/v1/quick_input.py) | Loops `pivot_data` (1..N kuitansi) → `source="quick_input"` |
| | [`app/api/v1/pengeluaran_ocr.py:/pengeluaran/ocr-save`](app/api/v1/pengeluaran_ocr.py) | Single increment → `source="pengeluaran_ocr"` (counter name stays `kuitansi_created` — metric tracks transaction creation volume across sources) |
| `observe_ai_inference(provider, model)` (cm) | [`app/ai_engine/local_ocr.py:extract_with_ollama`](app/ai_engine/local_ocr.py) | provider=`"ollama_local"`, model=`settings.OLLAMA_MODEL`. Outcomes: `ok` / `error` |
| | [`app/ai_engine/cloud_parser.py:validate_with_gemini`](app/ai_engine/cloud_parser.py) | provider=`"gemini"`, model=`settings.GEMINI_MODEL`. Outcomes: `ok` / `parse_fail` / `suspicious` / `error` |

---

## 6. /metrics Endpoint Design Choices

| Decision | Rationale |
|----------|-----------|
| Path: `/metrics` | Default Prometheus convention — every scrape config works out-of-the-box. |
| No auth required | Prometheus servers don't carry JWTs. Restricted at the **network** layer (nginx / firewall to internal scrape subnet) instead of the application layer. |
| Excluded from instrumentator middleware | [`excluded_handlers=["/metrics", "/health", ...]`](app/main.py:238) — otherwise every Prometheus scrape would inflate `http_request_duration_highr_seconds_count` by 1, masking the real traffic rate. |
| `include_in_schema=False` | `/metrics` is infra, not API. Doesn't belong in OpenAPI docs. |
| Wrapped in try/except | Observability must NEVER block startup. If `prometheus_client` or `prometheus-fastapi-instrumentator` fails to import (e.g., missing wheel in slim Docker image), the app still boots; we log a warning and continue. |
| Custom `REGISTRY` (not default) | See §4. Isolation + clean scrape output. |

---

## 7. Test Suite — `tests/test_t32_metrics.py`

**16 tests, all passing in 0.32s.**

```
tests/test_t32_metrics.py::test_registry_init_is_idempotent PASSED
tests/test_t32_metrics.py::test_record_security_event_increments_counter PASSED
tests/test_t32_metrics.py::test_log_security_event_hook_emits_counter PASSED
tests/test_t32_metrics.py::test_record_wa_blast_uses_unknown_for_empty_role PASSED
tests/test_t32_metrics.py::test_record_kuitansi_created_across_sources PASSED
tests/test_t32_metrics.py::test_observe_ai_inference_records_histogram PASSED
tests/test_t32_metrics.py::test_observe_ai_inference_records_on_exception PASSED
tests/test_t32_metrics.py::test_observe_ai_inference_outcome_override_in_except PASSED
tests/test_t32_metrics.py::test_build_info_emits_service_and_version PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_returns_200 PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_contains_flipus_custom_metrics PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_contains_http_instrumentator_metrics PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_excludes_itself_from_request_counting PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_excludes_health_endpoint PASSED
tests/test_t32_metrics.py::test_metrics_endpoint_not_in_openapi_schema PASSED
tests/test_t32_metrics.py::test_flipus_kuitansi_created_appears_in_scrape PASSED
======================== 16 passed, 6 warnings in 0.32s ========================
```

### Coverage matrix

| Concern | Test |
|---------|------|
| Registry init safety (no duplicate-collector crash) | `test_registry_init_is_idempotent` |
| Counter increment via direct helper | `test_record_security_event_increments_counter` |
| Counter increment via logger hook (S5-1 regression) | `test_log_security_event_hook_emits_counter` |
| Counter label cardinality guard (`""` → `"unknown"`) | `test_record_wa_blast_uses_unknown_for_empty_role` |
| Counter label fan-out (multiple distinct sources) | `test_record_kuitansi_created_across_sources` |
| Histogram happy path | `test_observe_ai_inference_records_histogram` |
| Histogram records on exception (finally block) | `test_observe_ai_inference_records_on_exception` |
| Histogram outcome override in `except` (production pattern) | `test_observe_ai_inference_outcome_override_in_except` |
| `BUILD_INFO` gauge shape | `test_build_info_emits_service_and_version` |
| `/metrics` returns 200 + correct Content-Type | `test_metrics_endpoint_returns_200` |
| `/metrics` exposes custom `flipus_*` family | `test_metrics_endpoint_contains_flipus_custom_metrics` |
| `/metrics` exposes HTTP `http_*` family (instrumentator) | `test_metrics_endpoint_contains_http_instrumentator_metrics` |
| `/metrics` excluded from instrumentator's own counters | `test_metrics_endpoint_excludes_itself_from_request_counting` |
| `/health` excluded (otherwise skews dashboards) | `test_metrics_endpoint_excludes_health_endpoint` |
| `/metrics` not leaked into OpenAPI schema | `test_metrics_endpoint_not_in_openapi_schema` |
| End-to-end: counter increment → visible at `/metrics` | `test_flipus_kuitansi_created_appears_in_scrape` |

---

## 8. Grafana Dashboard — `ops/grafana/flipus-dashboard.json`

**13 panels across 4 row groups**, JSON validated, ready to import.

| Row | Panels | Purpose |
|-----|--------|---------|
| 0 (top stats) | Build / RPS / Error rate / Kuitansi 24h / WA success / AI p95 | At-a-glance SLO snapshot. Color-coded thresholds (green/yellow/red). |
| 1 (HTTP) | Request rate by status / Latency p50/p95/p99 | Detect traffic anomalies + latency regressions. |
| 2 (Business) | Kuitansi creations by source / WA blast by role+outcome / Security events | Business health: which entry points are being used, is the blast reliable, are we seeing attacks. |
| 3 (AI) | AI p50/p95 by provider / AI rate by provider+outcome | Gemini vs Ollama performance + success split. |
| 4 (Logs) | Linked Loki panel for ERROR/CRITICAL events | One-click drill-down from a metric spike to the underlying log lines. |

Refresh: 30s. Timezone: Asia/Makassar (matches production user base). Templating: `${DS_PROMETHEUS}` + `${DS_LOKI}` so dashboard works in any Grafana with both datasources configured.

### 8.1 Useful PromQL queries

```promql
# HTTP 5xx error rate (alerts below)
sum(rate(http_request_duration_highr_seconds_count{status=~"5.."}[5m]))
  / clamp_min(sum(rate(http_request_duration_highr_seconds_count[5m])), 1)

# WA blast success rate per role
sum by (target_role) (rate(flipus_wa_blast_total{outcome="sent"}[1h]))
  / clamp_min(sum by (target_role) (rate(flipus_wa_blast_total[1h])), 1)

# Kuitansi creation throughput (24h, per source)
sum by (source) (increase(flipus_kuitansi_created_total{outcome="ok"}[24h]))

# AI p95 latency per provider
histogram_quantile(0.95,
  sum by (provider, le) (rate(flipus_ai_inference_seconds_bucket[5m])))

# Failed logins per minute (security KPI)
sum(rate(flipus_security_events_total{event="login_failed"}[1m])) * 60

# Which build is serving us right now
flipus_build_info
```

These will become alert definitions in S5-8 (Disaster Recovery + Runbook).

---

## 9. Dependencies Added

`requirements.txt`:
```text
prometheus-client>=0.20.0     # already present (transitive via starlette_exporter etc.)
prometheus-fastapi-instrumentator>=0.16.0   # ← added in S5-2
```

Both are pure-Python, no native deps, no system libs.

---

## 10. What This Sprint Did NOT Do (deferred to later sprints)

| Deferred | Sprint |
|----------|--------|
| Alertmanager rules for the 6 SLO panels | S5-8 (DR + Runbook) |
| Per-tenant metric labels (would blow cardinality budget) | Not planned — use Loki + request_id for tenant drilldown |
| Tracing (OpenTelemetry) | Not in FASE 5 scope — defer to FASE 6+ |
| Histogram buckets per-endpoint | Current default buckets are fine for "is it slow?"; per-endpoint optimization comes when we have a real p99 violation |
| Push gateway for batch jobs | FLIPUS has no batch jobs in production (all request/response); not needed |

---

## 11. Files Touched

**New:**
- [`app/core/metrics.py`](app/core/metrics.py) — 213 lines. The 4 metrics, BUILD_INFO, helpers, context manager.
- [`tests/test_t32_metrics.py`](tests/test_t32_metrics.py) — 16 tests.
- [`ops/grafana/flipus-dashboard.json`](ops/grafana/flipus-dashboard.json) — Grafana 10+ dashboard model.
- `FASE5_SPRINT2_SUMMARY.md` (this file).

**Modified:**
- [`app/main.py`](app/main.py) — added `/metrics` endpoint + `Instrumentator` + custom `REGISTRY` wiring.
- [`app/services/whatsapp.py`](app/services/whatsapp.py) — `_record_wa_blast_metric()` helper + 3 send functions take `target_role` param + 4 return points per function call the helper.
- [`app/api/v1/scanner.py`](app/api/v1/scanner.py) — `record_kuitansi_created(source="scanner_batch", ...)` after batch commit.
- [`app/api/v1/quick_input.py`](app/api/v1/quick_input.py) — `record_kuitansi_created(source="quick_input", ...)` in loop.
- [`app/api/v1/pengeluaran_ocr.py`](app/api/v1/pengeluaran_ocr.py) — single increment `source="pengeluaran_ocr"`.
- [`app/ai_engine/local_ocr.py`](app/ai_engine/local_ocr.py) — wrap `extract_with_ollama` in `observe_ai_inference(provider="ollama_local")`.
- [`app/ai_engine/cloud_parser.py`](app/ai_engine/cloud_parser.py) — split `validate_with_gemini` into outer (wraps with `observe_ai_inference`) + `_validate_with_gemini_impl` (calls `obs.set_outcome(...)`).
- [`requirements.txt`](requirements.txt) — added `prometheus-fastapi-instrumentator`.

---

## 12. Next: FASE 5 Sprint 3 — CI Pipeline

Goals:
- GitHub Actions workflow: lint (ruff) + test (pytest) + security (bandit + safety)
- PR-blocking on lint or test failure
- Coverage gate (fail if < current 69.2%)
- Secrets scanning (gitleaks or trufflehog)

Estimated complexity: small (1 workflow YAML + tweaks to pyproject for ruff config).
---

## 13. Bonus Fix — ContextVar Identity Bug (S5-2 regression catch)

While running the final FASE 5 regression sweep (`test_t31_logging + test_t32_metrics + test_t32_cors + test_t33_jwt_refresh` in a single pytest run), 2 CORS tests failed:

```
test_cors_x_request_id_echoed_in_response   FAILED (assert '-' == 'test-corr-id-12345')
test_cors_x_request_id_exposed_in_actual_response FAILED (len('-') >= 8)
```

### Root cause

[`tests/test_t31_logging.py:309-319`](tests/test_t31_logging.py:304) (`test_s51_service_identity_env_override`) calls `importlib.reload(app.core.logger)` to pick up new env-var values. After reload, `app.core.logger.request_id_var` is a **NEW `ContextVar` object**, but [`app/core/request_context.py:26`](app/core/request_context.py:26) had done:

```python
from app.core.logger import (
    request_id_var,  # ← captured OLD object
    ...
)
```

Result during middleware dispatch after the reload:

| line | code | which contextvar |
|---|---|---|
| [`request_context.py:62`](app/core/request_context.py:62) | `set_request_context(...)` | NEW (writes go here) |
| [`request_context.py:63`](app/core/request_context.py:63) | `request.state.request_id = request_id_var.get()` | OLD (default `-`) |
| [`request_context.py:99`](app/core/request_context.py:99) | `response.headers["X-Request-ID"] = request_id_var.get()` | OLD (default `-`) |

`auth.py:329-331` had the same anti-pattern with `tenant_id_var` / `user_id_var`.

### Fix

Both files now import the **module** (not the symbols) and resolve the contextvars through the module attribute — this way `importlib.reload()` produces the live module dict, and our reads/writes always go through the current `ContextVar` instance.

- [`app/core/request_context.py:25`](app/core/request_context.py:25) — module import + `_rid()`/`_set_rid()`/etc. helpers
- [`app/api/v1/auth.py:329`](app/api/v1/auth.py:329) — same pattern for tenant/user_id

### Verification

| run | before fix | after fix |
|---|---|---|
| full FASE 5 sweep (4 files) | **2 failed, 68 passed** | **70/70 passed** |
| full project (all test files) | n/a | **461/461 passed in 159.7s** |

Bonus value: S5-3 (CI Pipeline) will now run the full pytest reliably — the flake that would have made CI red on PR builds is now gone.
