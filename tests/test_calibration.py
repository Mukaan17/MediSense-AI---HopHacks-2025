"""Temperature scaling: fitting recovers a known miscalibration, ranking
is preserved, and the identity fallback is safe."""

import math
import random

from core.calibration import TemperatureScaler, expected_calibration_error


def _synthetic(n=2000, true_t=2.5, seed=7):
    """Overconfident logits: true probabilities come from logit/true_t, but
    the model emits the unscaled logit."""
    rng = random.Random(seed)
    logits, labels = [], []
    for _ in range(n):
        z = rng.uniform(-6, 6)
        p_true = 1.0 / (1.0 + math.exp(-z / true_t))
        logits.append(z)
        labels.append(1 if rng.random() < p_true else 0)
    return logits, labels


def test_fit_recovers_temperature():
    logits, labels = _synthetic(true_t=2.5)
    scaler = TemperatureScaler().fit(logits, labels)
    assert 2.0 < scaler.temperature < 3.1


def test_calibration_reduces_ece():
    logits, labels = _synthetic(true_t=3.0)
    raw = [1.0 / (1.0 + math.exp(-z)) for z in logits]
    scaler = TemperatureScaler().fit(logits, labels)
    calibrated = scaler.calibrate(logits)
    assert expected_calibration_error(calibrated, labels) < \
        expected_calibration_error(raw, labels)


def test_ranking_preserved():
    logits = [-2.0, -0.5, 0.1, 1.7, 4.2]
    probs = TemperatureScaler(3.3).calibrate(logits)
    assert probs == sorted(probs)


def test_identity_fallback_when_file_missing(tmp_path):
    scaler = TemperatureScaler.load(str(tmp_path / "nope.json"))
    assert scaler.temperature == 1.0
    p = scaler.calibrate([0.0])[0]
    assert abs(p - 0.5) < 1e-9


def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "cal.json")
    TemperatureScaler(1.7).save(path)
    assert TemperatureScaler.load(path).temperature == 1.7


def test_model_gate_rejects_regression(tmp_path):
    import subprocess
    import sys
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text("metrics:\n  val_macro_auroc: 0.60\n")
    r = subprocess.run(
        [sys.executable, "scripts/model_gate.py", "imaging_cxr", str(candidate)],
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "REGRESSION" in r.stdout


def test_model_gate_accepts_improvement(tmp_path):
    import subprocess
    import sys
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text("metrics:\n  val_macro_auroc: 0.85\n")
    r = subprocess.run(
        [sys.executable, "scripts/model_gate.py", "imaging_cxr", str(candidate)],
        capture_output=True, text=True)
    assert r.returncode == 0
    assert "passes" in r.stdout
