#!/usr/bin/env python3
"""Model eval gate: compare a candidate registry entry against the current
one and exit non-zero if any recorded metric regresses beyond tolerance.

Usage:
  python scripts/model_gate.py imaging_cxr candidate.yaml [--tolerance 0.01]

candidate.yaml holds one entry in the same shape as models/registry.yaml's
`current`. On success, promote by moving the candidate under `current`
(reviewed commit), keeping the old entry under `previous`.
"""

import argparse
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "models" / "registry.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="Model eval regression gate")
    parser.add_argument("model", help="registry key, e.g. imaging_cxr")
    parser.add_argument("candidate", help="YAML file with the candidate entry")
    parser.add_argument("--tolerance", type=float, default=0.01,
                        help="allowed metric drop before failing (default 0.01)")
    args = parser.parse_args()

    registry = yaml.safe_load(REGISTRY.read_text()) or {}
    entry = registry.get(args.model)
    if not entry or "current" not in entry:
        print(f"[gate] no current entry for {args.model!r} in {REGISTRY}")
        return 2
    current_metrics = (entry["current"].get("metrics") or {})

    candidate = yaml.safe_load(Path(args.candidate).read_text()) or {}
    candidate_metrics = (candidate.get("metrics") or {})

    if not candidate_metrics:
        print("[gate] candidate has no metrics; refusing to promote blind")
        return 2

    failures = []
    for name, current_value in current_metrics.items():
        if name not in candidate_metrics:
            failures.append(f"metric {name!r} missing from candidate")
            continue
        drop = float(current_value) - float(candidate_metrics[name])
        if drop > args.tolerance:
            failures.append(
                f"{name}: {current_value} -> {candidate_metrics[name]} "
                f"(drop {drop:.4f} > tolerance {args.tolerance})")

    if failures:
        print("[gate] REGRESSION - candidate rejected:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[gate] candidate passes: no metric regresses beyond tolerance")
    for name, value in candidate_metrics.items():
        marker = "=" if name in current_metrics else "+"
        print(f"  {marker} {name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
