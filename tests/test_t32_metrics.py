"""FASE 5 Sprint 2 — Prometheus /metrics endpoint + custom flipus_* metrics.

Memverifikasi:
  1. Registry init idempotent (no duplicate-collector crash on reimport)
  2. record_security_event() increments Counter + log_security_event() hook
  3. record_wa_blast() increments with target_role + outcome labels
  4. record_kuitansi_created() increments across sources
  5. observe_ai_inference() context manager records histogram + allows set_outcome
  6. observe_ai_inference() on exception still records histogram (outcome="error")
  7. BUILD_INFO gauge emits service + version labels (always=1)
  8. /metrics endpoint returns 200 with text/plain Prometheus exposition format
  9. /metrics contains both flipus_* custom AND http_* instrumentator metrics
 10. /metrics is excluded from instrumentator middleware (no self-counting)

Mengikuti konvensi FASE 5: test_t31_logging.py (S5-1), test_t32_*.py (S5-2 etc).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scrape(client: TestClient) -> str:
    """Hit /metrics and return body as text."""
    r = client.get("/metrics")
    assert r.status_code == 200, f"/metrics returned {r.status_code}"
    return r.text


def _value_for(text: str, metric_name: str, **labels) -> float | None:
    """Extract Counter/Histogram sum value matching all labels.

    Returns None if no match found. Labels must be alphabetical (Prometheus order).
    """
    if labels:
        # Build label fragment like {key1="v1",key2="v2"} (alphabetical)
        sorted_labels = sorted(labels.items())
        label_str = "{" + ",".join(f'{k}="{v}"' for k, v in sorted_labels) + "}"
    else:
        label_str = ""

    pattern = rf"^{re.escape(metric_name)}{re.escape(label_str)}\s+([0-9eE+\-\.]+)$"
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        m = re.match(pattern, line)
        if m:
            return float(m.group(1))
    return None


def _has_any(text: str, prefix: str) -> bool:
    return any(line.startswith(prefix) and not line.startswith(f"# {prefix}") for line in text.splitlines())


# ---------------------------------------------------------------------------
# Unit tests — registry + helpers
# ---------------------------------------------------------------------------


def test_registry_init_is_idempotent():
    """Re-calling _init_metrics_once() must NOT crash with 'Duplicated timeseries'.

    This guards against the classic prometheus_client foot-gun where reimporting
    the module or re-running app startup tries to register the same metric twice.
    """
    # Sanity: REGISTRY is a CollectorRegistry
    from prometheus_client import CollectorRegistry

    from app.core.metrics import REGISTRY, _init_metrics_once
    assert isinstance(REGISTRY, CollectorRegistry)

    # Run twice — must be safe.
    _init_metrics_once()
    _init_metrics_once()
    _init_metrics_once()


def test_record_security_event_increments_counter():
    """record_security_event() increments flipus_security_events_total."""
    from app.core.metrics import record_security_event

    before = record_security_event.__module__
    assert before == "app.core.metrics"

    # Generate a unique label pair so we don't collide with concurrent test runs
    # in the same process. Counter labels are mutable across tests.
    event = "t32_unit_test"
    outcome = "ok"
    record_security_event(event=event, outcome=outcome)
    # Re-import to read counter value via its registry collector
    from app.core.metrics import SECURITY_EVENTS

    samples = list(SECURITY_EVENTS.collect()[0].samples)
    matching = [s for s in samples if s.name == "flipus_security_events_total"
                and s.labels.get("event") == event and s.labels.get("outcome") == outcome]
    assert len(matching) == 1, f"expected exactly 1 matching sample, got {len(matching)}"
    assert matching[0].value >= 1.0


def test_log_security_event_hook_emits_counter():
    """log_security_event() (used by app code) auto-calls record_security_event().

    Regression: in S5-1 we wired logger.log_security_event() to also bump the
    security counter. This test pins that wiring so a future logger refactor
    doesn't silently break it.
    """
    from app.core.logger import log_security_event
    from app.core.metrics import SECURITY_EVENTS

    # Signature is log_security_event(event_type, *, request=None, user_id=None,
    # tenant_id=None, detail=""). The metric label `outcome` defaults to "ok"
    # in log_security_event itself.
    event_type = "t32_hook_test"

    before_samples = [s for s in SECURITY_EVENTS.collect()[0].samples
                      if s.name == "flipus_security_events_total"
                      and s.labels.get("event") == event_type
                      and s.labels.get("outcome") == "ok"]
    before = before_samples[0].value if before_samples else 0.0

    log_security_event(event_type)

    after_samples = [s for s in SECURITY_EVENTS.collect()[0].samples
                     if s.name == "flipus_security_events_total"
                     and s.labels.get("event") == event_type
                     and s.labels.get("outcome") == "ok"]
    assert len(after_samples) == 1
    assert after_samples[0].value == before + 1.0


def test_record_wa_blast_uses_unknown_for_empty_role():
    """Empty/None target_role must normalize to 'unknown' (cardinality guard)."""
    from app.core.metrics import WA_BLAST, record_wa_blast

    record_wa_blast(target_role="", outcome="skipped")
    record_wa_blast(target_role=None, outcome="sent")  # type: ignore[arg-type]

    samples = [s for s in WA_BLAST.collect()[0].samples
               if s.labels.get("target_role") == "unknown"]
    labels = {(s.labels.get("outcome")) for s in samples}
    # Both "" and None should have collapsed to "unknown"
    assert "skipped" in labels
    assert "sent" in labels


def test_record_kuitansi_created_across_sources():
    """record_kuitansi_created() accepts multiple distinct source labels."""
    from app.core.metrics import KUITANSI_CREATED, record_kuitansi_created

    record_kuitansi_created(source="t32_unit_a", outcome="ok")
    record_kuitansi_created(source="t32_unit_b", outcome="ok")
    record_kuitansi_created(source="t32_unit_c", outcome="failed")

    samples = [s for s in KUITANSI_CREATED.collect()[0].samples
               if s.name == "flipus_kuitansi_created_total"
               and s.labels.get("source", "").startswith("t32_unit_")]
    sources = {(s.labels.get("source"), s.labels.get("outcome")) for s in samples}
    assert ("t32_unit_a", "ok") in sources
    assert ("t32_unit_b", "ok") in sources
    assert ("t32_unit_c", "failed") in sources


def test_observe_ai_inference_records_histogram():
    """observe_ai_inference() should record a histogram observation."""
    import time

    from app.core.metrics import AI_INFERENCE_SECONDS, observe_ai_inference

    with observe_ai_inference(provider="t32_provider", model="t32_model") as obs:
        time.sleep(0.005)
        obs.set_outcome("ok")

    samples = list(AI_INFERENCE_SECONDS.collect()[0].samples)
    count_samples = [s for s in samples
                     if s.name == "flipus_ai_inference_seconds_count"
                     and s.labels.get("provider") == "t32_provider"
                     and s.labels.get("model") == "t32_model"
                     and s.labels.get("outcome") == "ok"]
    assert len(count_samples) == 1
    assert count_samples[0].value >= 1.0


def test_observe_ai_inference_records_on_exception():
    """Exception path: histogram still records (finally block).

    Outcome defaults to the ctor arg ('ok' by default) — caller is responsible
    for calling obs.set_outcome('error') in their except block. local_ocr.py
    and cloud_parser.py do this correctly; this test pins the contract.
    """
    from app.core.metrics import AI_INFERENCE_SECONDS, observe_ai_inference

    provider = "t32_provider_exc"
    model = "t32_model_exc"

    with pytest.raises(RuntimeError):
        with observe_ai_inference(provider=provider, model=model):
            raise RuntimeError("simulated AI failure")
            # No set_outcome() — should default to "ok"

    samples = list(AI_INFERENCE_SECONDS.collect()[0].samples)
    # Histogram count for outcome="ok" should be >= 1 even though an exception
    # was raised — the finally block always observes.
    ok_samples = [s for s in samples
                  if s.name == "flipus_ai_inference_seconds_count"
                  and s.labels.get("provider") == provider
                  and s.labels.get("model") == model
                  and s.labels.get("outcome") == "ok"]
    assert len(ok_samples) == 1
    assert ok_samples[0].value >= 1.0


def test_observe_ai_inference_outcome_override_in_except():
    """Caller can call obs.set_outcome('error') inside except — it overrides default.

    This is the pattern used in app/ai_engine/local_ocr.py and cloud_parser.py.
    """
    from app.core.metrics import AI_INFERENCE_SECONDS, observe_ai_inference

    provider = "t32_provider_overr"
    model = "t32_model_overr"

    with pytest.raises(RuntimeError):
        with observe_ai_inference(provider=provider, model=model) as obs:
            try:
                raise RuntimeError("simulated AI failure")
            except RuntimeError:
                obs.set_outcome("error")
                raise

    samples = list(AI_INFERENCE_SECONDS.collect()[0].samples)
    err_samples = [s for s in samples
                   if s.name == "flipus_ai_inference_seconds_count"
                   and s.labels.get("provider") == provider
                   and s.labels.get("model") == model
                   and s.labels.get("outcome") == "error"]
    assert len(err_samples) == 1
    assert err_samples[0].value >= 1.0


def test_build_info_emits_service_and_version():
    """flipus_build_info gauge must have service + version labels with value=1."""
    from app.core.metrics import BUILD_INFO, SERVICE_NAME, SERVICE_VERSION

    samples = list(BUILD_INFO.collect()[0].samples)
    matching = [s for s in samples
                if s.name == "flipus_build_info"
                and s.labels.get("service") == SERVICE_NAME
                and s.labels.get("version") == SERVICE_VERSION]
    assert len(matching) == 1
    assert matching[0].value == 1.0


# ---------------------------------------------------------------------------
# Integration tests — /metrics endpoint
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200(client):
    """GET /metrics must return 200 with Prometheus exposition format."""
    r = client.get("/metrics")
    assert r.status_code == 200
    # Content-Type should be text/plain; Prometheus convention
    ct = r.headers.get("content-type", "")
    assert "text/plain" in ct


def test_metrics_endpoint_contains_flipus_custom_metrics(client):
    """/metrics scrape must include all 4 flipus_* custom metrics families."""
    # Bump each metric so it's emitted in the scrape (counters with no .labels()
    # called don't appear until they're touched)
    from app.core.metrics import (
        observe_ai_inference,
        record_kuitansi_created,
        record_security_event,
    )
    record_security_event(event="t32_integration", outcome="ok")
    record_kuitansi_created(source="t32_integration", outcome="ok")
    with observe_ai_inference(provider="t32_int", model="t32_int") as obs:
        obs.set_outcome("ok")

    text = _scrape(client)

    # All 4 families must be present
    assert _has_any(text, "flipus_security_events_total")
    assert _has_any(text, "flipus_kuitansi_created_total")
    assert _has_any(text, "flipus_ai_inference_seconds_")  # _count, _sum, _bucket
    assert _has_any(text, "flipus_build_info")


def test_metrics_endpoint_contains_http_instrumentator_metrics(client):
    """/metrics scrape must include prometheus-fastapi-instrumentator's http_* metrics.

    This is the OTHER half of the registry fix: Instrumentator was wired to use
    our custom REGISTRY so its HTTP metrics land in the SAME scrape as our
    flipus_* business metrics.
    """
    # Trigger at least one HTTP request through instrumentator middleware
    client.get("/health")  # /health is excluded from instrumentator; use /docs maybe?
    # Use an arbitrary endpoint that's not in excluded_handlers
    client.get("/openapi.json")

    text = _scrape(client)

    # Instrumentator emits http_request_duration_highr_seconds_*, etc.
    assert _has_any(text, "http_request_duration_highr_seconds_")
    assert _has_any(text, "http_requests_inprogress") or _has_any(text, "http_request_duration")


def test_metrics_endpoint_excludes_itself_from_request_counting(client):
    """/metrics must NOT appear in instrumentator's http_request_* counters.

    Without this, every Prometheus scrape would inflate our request-rate metric.
    excluded_handlers in app/main.py handles this.
    """
    # Hit /metrics twice; then scrape again and confirm /metrics handler
    # did not get counted.
    client.get("/metrics")
    client.get("/metrics")
    text = _scrape(client)

    # Look for handler="/metrics" label inside http_request_duration_highr_seconds_count
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith("http_request_duration_highr_seconds_count"):
            continue
        if 'handler="/metrics"' in line:
            pytest.fail(f"/metrics is being counted by instrumentator: {line}")


def test_metrics_endpoint_excludes_health_endpoint(client):
    """GET /health must NOT appear in instrumentator's http_request_* counters.

    Health checks fire every 10s — including them would massively skew
    request-rate dashboards.
    """
    client.get("/health")
    client.get("/health")
    text = _scrape(client)

    for line in text.splitlines():
        if line.startswith("#") or not line.startswith("http_request_duration_highr_seconds_count"):
            continue
        if 'handler="/health"' in line:
            pytest.fail(f"/health is being counted by instrumentator: {line}")


def test_metrics_endpoint_not_in_openapi_schema(client):
    """/metrics must NOT appear in OpenAPI docs (it's an infra endpoint, not an API)."""
    schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema.get("paths", {}), \
        "/metrics leaked into OpenAPI — Prometheus infra endpoint should be excluded"


def test_flipus_kuitansi_created_appears_in_scrape(client):
    """End-to-end: hit a kuitansi endpoint, then verify counter shows up in /metrics.

    Uses a quick_increment via the public helper rather than going through a full
    HTTP request (which would require JWT + tenant setup). The helper is the
    same code path that scanner.py / quick_input.py call after db.commit().
    """
    from app.core.metrics import record_kuitansi_created

    source = "t32_e2e_smoke"
    record_kuitansi_created(source=source, outcome="ok")
    record_kuitansi_created(source=source, outcome="ok")
    record_kuitansi_created(source=source, outcome="ok")

    text = _scrape(client)
    # Prometheus sorts labels alphabetically: outcome before source
    val = _value_for(text, "flipus_kuitansi_created_total",
                     outcome="ok", source=source)
    assert val is not None, f"counter for {source} not found in scrape"
    assert val >= 3.0
