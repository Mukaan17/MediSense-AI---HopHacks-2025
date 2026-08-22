"""Metrics exporter (prometheus_client histograms), tracing no-op path,
and Sentry init guard."""

from core import metrics


def test_counter_exports_with_total_suffix():
    metrics.inc("obs_test_counter", provider="x")
    out = metrics.render_prometheus()
    assert 'medisense_obs_test_counter_total{provider="x"}' in out


def test_latency_exports_histogram_buckets():
    metrics.observe("obs_test_latency", 42.0, stage="extract")
    out = metrics.render_prometheus()
    # Real buckets, so alert rules can use histogram_quantile.
    assert 'medisense_obs_test_latency_ms_bucket{le="50.0",stage="extract"}' in out
    assert 'medisense_obs_test_latency_ms_count{stage="extract"}' in out
    assert 'medisense_obs_test_latency_ms_sum{stage="extract"}' in out


def test_timed_context_manager_observes():
    with metrics.timed("obs_test_timed", stage="fuse"):
        pass
    out = metrics.render_prometheus()
    assert 'medisense_obs_test_timed_ms_count{stage="fuse"} 1.0' in out


def test_label_schema_coercion_never_raises():
    metrics.inc("obs_test_schema", provider="a")
    # Different label set on the same metric: coerced, not crashed.
    metrics.inc("obs_test_schema", model="b")
    metrics.inc("obs_test_schema")
    out = metrics.render_prometheus()
    assert 'medisense_obs_test_schema_total{provider="a"} 1.0' in out
    assert 'medisense_obs_test_schema_total{provider=""} 2.0' in out


def test_metrics_endpoint_serves_exposition(client):
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "medisense_requests_total" in r.text
    assert "medisense_request_latency_ms_bucket" in r.text


def test_tracing_noop_without_endpoint(monkeypatch):
    from core import tracing
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    tracing.reset_for_tests()
    with tracing.span("unit", key="value") as s:
        assert s is None
    tracing.reset_for_tests()


def test_sentry_inert_without_dsn(monkeypatch):
    from core.error_tracking import maybe_init_sentry
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert maybe_init_sentry() is False


def test_sentry_initializes_with_dsn(monkeypatch):
    import sys
    import types

    captured = {}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kwargs: captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    monkeypatch.setenv("SENTRY_DSN", "https://examplekey@o0.ingest.example/0")

    from core.error_tracking import maybe_init_sentry
    assert maybe_init_sentry() is True
    assert captured["dsn"].startswith("https://")
    # Clinical posture: PII and local variables must stay off.
    assert captured["send_default_pii"] is False
    assert captured["include_local_variables"] is False
