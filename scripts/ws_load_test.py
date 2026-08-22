#!/usr/bin/env python3
"""WebSocket load test for the live-case pipeline.

Simulates N concurrent live cases, each sending M utterances, and reports
per-utterance HUD latency percentiles. Run against a server started with the
same configuration you intend to deploy (LLM keys optional - without them
the coach step degrades but the pipeline still runs).

Usage:
  python3 scripts/ws_load_test.py --base-url http://localhost:8000 \
      --cases 10 --utterances 5 [--token <bearer>]
"""

import argparse
import asyncio
import json
import statistics
import time

import requests

UTTERANCES = [
    "I have had a bad cough and fever for three days",
    "the cough is getting worse at night",
    "I feel short of breath when climbing stairs",
    "no chest pain but I feel very tired",
    "my temperature this morning was one hundred and one",
]


async def run_case(base_ws: str, case_id: str, n_utterances: int, token: str,
                   latencies: list) -> None:
    import websockets

    url = f"{base_ws}/ws/case/{case_id}" + (f"?token={token}" if token else "")
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()  # initial HUD
        for i in range(n_utterances):
            text = UTTERANCES[i % len(UTTERANCES)]
            start = time.perf_counter()
            await ws.send(json.dumps({"utterance": text, "speaker": "patient"}))
            # Consume streaming tokens until the full HUD arrives
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") != "streaming_token":
                    break
            latencies.append((time.perf_counter() - start) * 1000)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Live-case WS load test")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cases", type=int, default=10)
    parser.add_argument("--utterances", type=int, default=5)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    case_ids = []
    for _ in range(args.cases):
        r = requests.post(f"{args.base_url}/api/case/voice?live=1", headers=headers, timeout=30)
        r.raise_for_status()
        case_ids.append(r.json()["case_id"])

    base_ws = args.base_url.replace("http://", "ws://").replace("https://", "wss://")
    latencies: list = []
    started = time.perf_counter()
    await asyncio.gather(*[
        run_case(base_ws, cid, args.utterances, args.token, latencies)
        for cid in case_ids
    ])
    wall = time.perf_counter() - started

    latencies.sort()
    p = lambda q: latencies[min(len(latencies) - 1, int(q * len(latencies)))]
    print(f"cases={args.cases} utterances/case={args.utterances} "
          f"total={len(latencies)} wall={wall:.1f}s")
    print(f"per-utterance HUD latency ms: "
          f"p50={p(0.50):.0f} p90={p(0.90):.0f} p95={p(0.95):.0f} "
          f"max={latencies[-1]:.0f} mean={statistics.mean(latencies):.0f}")


if __name__ == "__main__":
    asyncio.run(main())
