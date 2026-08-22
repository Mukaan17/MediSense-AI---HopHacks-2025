# -*- coding: utf-8 -*-
"""Probability calibration for model heads.

The imaging head's raw scores feed fusion as if they were probabilities;
temperature scaling (Guo et al. 2017) is the standard single-parameter fix:
fit T on a held-out set's logits/labels, then divide logits by T before the
sigmoid/softmax. One parameter, preserves ranking (AUROC unchanged),
improves calibration (ECE).

Usage (offline, once per checkpoint):
    scaler = TemperatureScaler().fit(val_logits, val_labels)
    scaler.save("models/calibration_cxr.json")
Runtime:
    scaler = TemperatureScaler.load(path)   # T=1.0 when file absent
    probs = scaler.calibrate(logits)
"""

import json
import logging
import math
import os
from typing import List, Sequence

log = logging.getLogger("core.calibration")


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class TemperatureScaler:
    """Single-temperature calibration for independent (multi-label) logits.

    Implemented dependency-free (golden-section search on NLL) so the
    runtime path never needs torch; fitting a 1-D convex objective this way
    matches LBFGS to well under measurement noise."""

    def __init__(self, temperature: float = 1.0):
        self.temperature = float(temperature)

    # ---- fitting ----

    @staticmethod
    def _nll(logits: Sequence[float], labels: Sequence[int], t: float) -> float:
        total = 0.0
        eps = 1e-12
        for x, y in zip(logits, labels):
            p = _sigmoid(x / t)
            p = min(max(p, eps), 1.0 - eps)
            total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
        return total / max(1, len(logits))

    def fit(self, logits: Sequence[float], labels: Sequence[int],
            t_min: float = 0.05, t_max: float = 10.0, iters: int = 80) -> "TemperatureScaler":
        if len(logits) != len(labels) or not logits:
            raise ValueError("logits and labels must be non-empty and equal length")
        gr = (math.sqrt(5.0) - 1.0) / 2.0
        a, b = t_min, t_max
        c = b - gr * (b - a)
        d = a + gr * (b - a)
        fc = self._nll(logits, labels, c)
        fd = self._nll(logits, labels, d)
        for _ in range(iters):
            if fc < fd:
                b, d, fd = d, c, fc
                c = b - gr * (b - a)
                fc = self._nll(logits, labels, c)
            else:
                a, c, fc = c, d, fd
                d = a + gr * (b - a)
                fd = self._nll(logits, labels, d)
        self.temperature = (a + b) / 2.0
        return self

    # ---- runtime ----

    def calibrate(self, logits: Sequence[float]) -> List[float]:
        t = self.temperature or 1.0
        return [_sigmoid(x / t) for x in logits]

    # ---- persistence ----

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump({"temperature": self.temperature}, f)

    @classmethod
    def load(cls, path: str) -> "TemperatureScaler":
        """Identity scaler (T=1.0) when no calibration file exists - safe to
        call unconditionally at model load."""
        if not path or not os.path.exists(path):
            return cls(1.0)
        try:
            with open(path) as f:
                return cls(float(json.load(f).get("temperature", 1.0)))
        except Exception as e:
            log.warning(f"[calibration] unreadable {path}: {e}; using T=1.0")
            return cls(1.0)


def expected_calibration_error(probs: Sequence[float], labels: Sequence[int],
                               bins: int = 10) -> float:
    """Standard ECE over equal-width confidence bins."""
    if not probs:
        return 0.0
    bucket_conf = [0.0] * bins
    bucket_acc = [0.0] * bins
    bucket_n = [0] * bins
    for p, y in zip(probs, labels):
        b = min(bins - 1, int(p * bins))
        bucket_conf[b] += p
        bucket_acc[b] += y
        bucket_n[b] += 1
    n = len(probs)
    ece = 0.0
    for b in range(bins):
        if bucket_n[b]:
            ece += (bucket_n[b] / n) * abs(
                bucket_acc[b] / bucket_n[b] - bucket_conf[b] / bucket_n[b])
    return ece
