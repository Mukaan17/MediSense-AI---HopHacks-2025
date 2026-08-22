# -*- coding: utf-8 -*-
"""OpenTelemetry scaffolding: a `span` context manager that is a strict
no-op unless BOTH the opentelemetry packages are installed AND
OTEL_EXPORTER_OTLP_ENDPOINT is set. The hot path never pays for tracing
that isn't configured.

Install the exporter stack with `pip install -r
requirements-observability.txt`; point OTEL_EXPORTER_OTLP_ENDPOINT at an
OTLP/HTTP collector.
"""

import logging
import os
from contextlib import contextmanager, nullcontext

log = logging.getLogger("core.tracing")

_tracer = None
_init_attempted = False


def _get_tracer():
    global _tracer, _init_attempted
    if _tracer is not None or _init_attempted:
        return _tracer
    _init_attempted = True
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider = TracerProvider(resource=Resource.create(
            {"service.name": os.getenv("OTEL_SERVICE_NAME", "medisense-backend")}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("medisense")
        log.info("[tracing] OTLP exporter configured")
    except Exception as e:
        log.warning(f"[tracing] disabled ({e})")
        _tracer = None
    return _tracer


def reset_for_tests() -> None:
    """Drop cached tracer state so tests can flip env vars."""
    global _tracer, _init_attempted
    _tracer = None
    _init_attempted = False


@contextmanager
def span(name: str, **attributes):
    tracer = _get_tracer()
    if tracer is None:
        with nullcontext():
            yield None
        return
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            try:
                s.set_attribute(k, str(v))
            except Exception:
                pass
        yield s
