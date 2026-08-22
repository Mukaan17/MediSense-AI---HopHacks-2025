# -*- coding: utf-8 -*-
"""In-process metrics: counters and latency aggregates, exported in
Prometheus text format at /metrics (auth-gated in clinical mode).

Deliberately dependency-free: count/sum/min/max per series is enough to
alert on and graph, and a real Prometheus client can replace this without
changing call sites."""

import threading
import time
from contextlib import contextmanager
from typing import Dict, Tuple

_lock = threading.Lock()
_counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
_timings: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, float]] = {}


def _key(name: str, labels: Dict[str, str]):
    return (name, tuple(sorted((labels or {}).items())))


def inc(name: str, value: float = 1.0, **labels) -> None:
    k = _key(name, labels)
    with _lock:
        _counters[k] = _counters.get(k, 0.0) + value


def observe(name: str, value_ms: float, **labels) -> None:
    k = _key(name, labels)
    with _lock:
        t = _timings.setdefault(k, {"count": 0, "sum_ms": 0.0, "min_ms": float("inf"), "max_ms": 0.0})
        t["count"] += 1
        t["sum_ms"] += value_ms
        t["min_ms"] = min(t["min_ms"], value_ms)
        t["max_ms"] = max(t["max_ms"], value_ms)


@contextmanager
def timed(name: str, **labels):
    start = time.perf_counter()
    try:
        yield
    finally:
        observe(name, (time.perf_counter() - start) * 1000, **labels)


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt_labels(labels: Tuple[Tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in labels)
    return "{" + inner + "}"


def render_prometheus() -> str:
    lines = []
    with _lock:
        for (name, labels), value in sorted(_counters.items()):
            lines.append(f"medisense_{name}_total{_fmt_labels(labels)} {value:g}")
        for (name, labels), t in sorted(_timings.items()):
            base = f"medisense_{name}"
            lab = _fmt_labels(labels)
            lines.append(f"{base}_count{lab} {t['count']:g}")
            lines.append(f"{base}_sum_ms{lab} {t['sum_ms']:.1f}")
            lines.append(f"{base}_max_ms{lab} {t['max_ms']:.1f}")
    return "\n".join(lines) + "\n"
