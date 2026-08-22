#!/usr/bin/env python3
"""STT model benchmark: latency and word error rate on the committed
speech fixture (known reference text). Informs the STT_LIVE_MODEL choice;
changing the model is a reviewed registry decision.

Usage:
  python scripts/stt_benchmark.py tiny.en base.en distil-small.en
"""

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "frontend" / "e2e" / "fixtures" / "utterance.wav"
REFERENCE = ("i have had a persistent cough and a high fever for three days "
             "i feel short of breath when climbing stairs")


def wer(hyp: str, ref: str) -> float:
    h = [w for w in hyp.lower().replace(".", " ").replace(",", " ").split() if w]
    r = [w for w in ref.split() if w]
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    return d[len(r)][len(h)] / max(1, len(r))


def main() -> int:
    parser = argparse.ArgumentParser(description="faster-whisper model benchmark")
    parser.add_argument("models", nargs="+", help="model names, e.g. tiny.en base.en")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    print(f"{'model':<18} {'load_s':>7} {'p50_s':>7} {'WER':>6}")
    for name in args.models:
        t0 = time.perf_counter()
        model = WhisperModel(name, device="cpu", compute_type="int8")
        load_s = time.perf_counter() - t0

        times = []
        text = ""
        for _ in range(args.runs):
            t0 = time.perf_counter()
            segments, _ = model.transcribe(str(FIXTURE), language="en",
                                           beam_size=1, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments)
            times.append(time.perf_counter() - t0)
        times.sort()
        p50 = times[len(times) // 2]
        print(f"{name:<18} {load_s:>7.1f} {p50:>7.2f} {wer(text, REFERENCE):>6.2f}")
        print(f"    -> {text[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(sys.exit(main()))
