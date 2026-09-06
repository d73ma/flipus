"""
FASE 5 Sprint 2 — Prometheus metrics: registry + 4 custom metrics.

Why centralize here (instead of inline `Counter(...)` at call site)?
  - All metrics share one `CollectorRegistry` instance so `/metrics` exposes
    them in one scrape.
  - `service` / `version` labels (from S5-1 constants) are applied at module
    load time — operator can filter by build (canary vs stable) without
    re-deploying Grafana queries.
  - Singleton guard via `_INIT_DONE` so test re-imports / `app.core.metrics`
    reloaded by `importlib.reload()` do NOT raise `Duplicated timeseries in
    CollectorRegistry` (real failure mode if you skip the guard).
  - Provides a single `observe_ai_inference(provider, model, outcome, seconds)`
    helper so the AI engine doesn't need to know about Histogram buckets.

Custom metrics (the "4" from the S5-2 scope):
  1. `flipus_security_events_total` — Counter, labels=(event, outcome).
     Wired into `app.core.logger.log_security_event()` so EVERY security log
     line ALSO increments this counter. Single source of truth for SOC alerts.

  2. `flipus_wa_blast_total` — Counter, labels=(target_role, outcome).
     Wired into `app.services.whatsapp.send_simple_message()` and friends.
     `outcome` ∈ {sent, failed, skipped, timeout}.

  3. `flipus_kuitansi_created_total` — Counter, labels=(source, outcome).
     Wired into scanner / quick_input / ocr endpoints. `source` ∈
     {scanner, quick_input, ocr, manual}. This is THE business KPI counter
     (SRE alert: "kuitansi_created_total dropped to 0 in last 10m" = someone
     can't input transactions).

  4. `flipus_ai_inference_seconds` — Histogram, labels=(provider, model, outcome).
     Observes Gemini (cloud) and Ollama (local) latency. Default Prometheus
     buckets are too coarse for our SLO (we want sub-second p95 visibility)
     so we override buckets.

HTTP auto-metrics (from `prometheus-fastapi-instrumentator`, configured in
`app.main.setup_metrics()`):
  - `http_requests_total{method,handler,status}` — Counter.
  - `http_request_duration_seconds{method,handler}` — Histogram.
  - `http_requests_inprogress` — Gauge.
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, Histogram

# S5-1 service identity — read at import time so the labels are baked in.
# We duplicate the import here (instead of `from app.core.logger import ...`)
# to AVOID a circular import: logger.py does NOT import metrics, and metrics
# only needs the two string constants, not the full logger machinery.
try:
    from app.core.logger import SERVICE_NAME, SERVICE_VERSION  # type: ignore
except Exception:  # pragma: no cover — logger not yet imported during bootstrap
    SERVICE_NAME = os.environ.get("FLIPUS_SERVICE_NAME", "flipus")
    SERVICE_VERSION = os.environ.get("FLIPUS_SERVICE_VERSION", "1.5.0")

# ---------------------------------------------------------------------------
# Registry (singleton).
# ---------------------------------------------------------------------------
# We use a CUSTOM CollectorRegistry (not the prometheus_client default) so
# we can register the 4 custom `flipus_*` metrics in isolation from any
# third-party libraries that may auto-register on the default registry.
#
# To make ALL metrics (custom + HTTP auto-metrics from
# `prometheus-fastapi-instrumentator`) appear in a single /metrics scrape,
# we pass `registry=REGISTRY` to the `Instrumentator(...)` constructor in
# `app/main.py`. The instrumentator library writes its http_request_duration,
# http_requests_inprogress, etc. metrics into OUR registry instead of the
# default one. Result: ONE scrape surface, two metric families, zero leakage.
REGISTRY = CollectorRegistry(auto_describe=True)

_INIT_DONE = False


def _init_metrics_once() -> None:
    """Idempotently register custom metrics. Safe to call multiple times."""
    global _INIT_DONE
    if _INIT_DONE:
        return

    # Apply service labels to registry metadata (visible in /metrics as HELP).
    # Note: Counter/Histogram themselves do NOT carry these as labels — they
    # are added per-observation via `.labels(service=..., version=...)` if
    # needed. For low-cardinality metrics (counters with ≤4 label values) we
    # do NOT add per-observation service labels to keep cardinality bounded.

    # 1. Security events
    global SECURITY_EVENTS
    SECURITY_EVENTS = Counter(
        "flipus_security_events_total",
        "Security-relevant events emitted via log_security_event().",
        labelnames=("event", "outcome"),
        registry=REGISTRY,
    )

    # 2. WhatsApp blast
    global WA_BLAST
    WA_BLAST = Counter(
        "flipus_wa_blast_total",
        "WhatsApp blast attempts grouped by target_role and outcome.",
        labelnames=("target_role", "outcome"),
        registry=REGISTRY,
    )

    # 3. Kuitansi created (business KPI)
    global KUITANSI_CREATED
    KUITANSI_CREATED = Counter(
        "flipus_kuitansi_created_total",
        "Kuitansi (transaction) creations grouped by source and outcome.",
        labelnames=("source", "outcome"),
        registry=REGISTRY,
    )

    # 4. AI inference latency (Histogram)
    # Custom buckets: tight around sub-second for SLO visibility.
    global AI_INFERENCE_SECONDS
    AI_INFERENCE_SECONDS = Histogram(
        "flipus_ai_inference_seconds",
        "Latency of AI inference (cloud + local).",
        labelnames=("provider", "model", "outcome"),
        buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
        registry=REGISTRY,
    )

    # Static info gauge (always 1) — emits service name + version on every
    # scrape so Grafana dashboard can show "which build is this?" without
    # a separate discovery job.
    from prometheus_client import Gauge
    global BUILD_INFO
    BUILD_INFO = Gauge(
        "flipus_build_info",
        "Static build info (always 1). Carries service + version labels.",
        labelnames=("service", "version"),
        registry=REGISTRY,
    )
    BUILD_INFO.labels(service=SERVICE_NAME, version=SERVICE_VERSION).set(1)

    _INIT_DONE = True


# Run init at module import. Idempotent.
_init_metrics_once()


# ---------------------------------------------------------------------------
# Public helpers — call these from production code, NOT the raw counters.
# ---------------------------------------------------------------------------

def record_security_event(event: str, outcome: str = "ok") -> None:
    """Increment `flipus_security_events_total{event, outcome}`.

    Called by `app.core.logger.log_security_event()` automatically.
    Direct callers (outside the logger) are rare — prefer log_security_event().
    """
    SECURITY_EVENTS.labels(event=event, outcome=outcome).inc()


def record_wa_blast(target_role: str, outcome: str) -> None:
    """Increment `flipus_wa_blast_total{target_role, outcome}`.

    Args:
        target_role: e.g. "BENDAHARA", "PENDETA", "KETUA_KEUANGAN".
        outcome: one of {"sent", "failed", "skipped", "timeout"}.
    """
    WA_BLAST.labels(target_role=target_role or "unknown", outcome=outcome).inc()


def record_kuitansi_created(source: str, outcome: str = "ok") -> None:
    """Increment `flipus_kuitansi_created_total{source, outcome}`.

    Args:
        source: one of {"scanner", "quick_input", "ocr", "manual", "api"}.
        outcome: "ok" or "failed".
    """
    KUITANSI_CREATED.labels(source=source, outcome=outcome).inc()


@contextmanager
def observe_ai_inference(provider: str, model: str, outcome: str = "ok") -> Iterator[None]:
    """Context manager: time an AI inference and record the histogram.

    Usage:
        with observe_ai_inference("gemini", "gemini-2.0-flash") as obs:
            result = call_gemini(...)
            if result.get("error"):
                obs.set_outcome("failed")
    """
    start = time.perf_counter()
    state = {"outcome": outcome}
    try:
        yield _OutcomeSetter(state)
    finally:
        elapsed = time.perf_counter() - start
        AI_INFERENCE_SECONDS.labels(
            provider=provider, model=model, outcome=state["outcome"],
        ).observe(elapsed)


class _OutcomeSetter:
    """Tiny helper so callers can override outcome on exception path.

    with observe_ai_inference("ollama", "llama3.2") as obs:
        try:
            ...
        except Exception:
            obs.set_outcome("failed")
            raise
    """
    __slots__ = ("_state",)

    def __init__(self, state: dict) -> None:
        self._state = state

    def set_outcome(self, outcome: str) -> None:
        self._state["outcome"] = outcome
