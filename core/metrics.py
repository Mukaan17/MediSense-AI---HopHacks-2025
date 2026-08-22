# -*- coding: utf-8 -*-
"""Process metrics on prometheus_client: counters and latency histograms,
exported in Prometheus text format at /metrics (auth-gated in clinical
mode).

The call-site API (inc / observe / timed / render_prometheus) is unchanged
from the earlier dependency-free implementation; what changed is the
export: histograms with real buckets, so alert rules can use
histogram_quantile instead of approximating percentiles with means.

Conventions:
- Counters export as  medisense_<name>_total{labels}
- Latencies export as medisense_<name>_ms_bucket/_count/_sum{labels}
- A metric's label set is fixed by its first use; later calls with
  different labels are coerced (missing -> "", extras dropped) with a
  one-time warning, because prometheus_client requires stable label names.

`timed` also opens an OpenTelemetry span (core.tracing) so stage timings
appear in traces when an OTLP endpoint is configured - a no-op otherwise.
"""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Dict, Tuple

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

log = logging.getLogger("core.metrics")

REGISTRY = CollectorRegistry()

# Milliseconds; wide enough for LLM calls, fine enough for pipeline stages.
LATENCY_BUCKETS_MS = (
    5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000,
)

_lock = threading.Lock()
_counters: Dict[str, Counter] = {}
_histograms: Dict[str, Histogram] = {}
_label_schema: Dict[str, Tuple[str, ...]] = {}
_schema_warned: set = set()


def _labelnames(name: str, labels: Dict[str, str]) -> Tuple[str, ...]:
    schema = _label_schema.get(name)
    if schema is None:
        schema = tuple(sorted(labels.keys()))
        _label_schema[name] = schema
    return schema


def _coerce(name: str, schema: Tuple[str, ...], labels: Dict[str, str]) -> Dict[str, str]:
    if tuple(sorted(labels.keys())) != schema and name not in _schema_warned:
        _schema_warned.add(name)
        log.warning("metric %r called with labels %s; schema is %s - coercing",
                    name, sorted(labels.keys()), list(schema))
    return {k: str(labels.get(k, "")) for k in schema}


def inc(name: str, value: float = 1.0, **labels) -> None:
    with _lock:
        schema = _labelnames(name, labels)
        counter = _counters.get(name)
        if counter is None:
            counter = Counter(f"medisense_{name}", f"{name} (counter)",
                              labelnames=schema, registry=REGISTRY)
            _counters[name] = counter
    coerced = _coerce(name, schema, labels)
    (counter.labels(**coerced) if schema else counter).inc(value)


def observe(name: str, value_ms: float, **labels) -> None:
    with _lock:
        schema = _labelnames(name, labels)
        hist = _histograms.get(name)
        if hist is None:
            hist = Histogram(f"medisense_{name}_ms", f"{name} latency (ms)",
                             labelnames=schema, buckets=LATENCY_BUCKETS_MS,
                             registry=REGISTRY)
            _histograms[name] = hist
    coerced = _coerce(name, schema, labels)
    (hist.labels(**coerced) if schema else hist).observe(value_ms)


@contextmanager
def timed(name: str, **labels):
    from core.tracing import span
    start = time.perf_counter()
    with span(name, **labels):
        try:
            yield
        finally:
            observe(name, (time.perf_counter() - start) * 1000, **labels)


def render_prometheus() -> str:
    return generate_latest(REGISTRY).decode("utf-8")
