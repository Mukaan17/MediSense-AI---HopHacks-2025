#!/usr/bin/env python3
"""End-to-end smoke test for the multimodal clinical backend.

Usage:
  python3 smoke_test.py
  python3 smoke_test.py --base-url http://localhost:8000
  python3 smoke_test.py --skip-voice --skip-ws
"""

import argparse
import asyncio
import io
import json
import os
import sys
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

try:
    import websockets
except Exception:
    websockets = None


DEFAULT_BASE_URL = "http://localhost:8000"


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test clinical backend endpoints.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL.")
    parser.add_argument("--timeout", type=int, default=45, help="HTTP timeout (seconds).")
    parser.add_argument("--image", default="", help="Optional image path to use for multimodal checks.")
    parser.add_argument("--skip-voice", action="store_true", help="Skip /voice_transcribe check.")
    parser.add_argument("--skip-ws", action="store_true", help="Skip websocket live-case check.")
    return parser.parse_args()


def find_default_image_path() -> Optional[str]:
    # Prefer EHR-linked image for stable image->EHR matching behavior.
    ehr_json = "ehr_with_images.json"
    if os.path.exists(ehr_json):
        try:
            with open(ehr_json, "r", encoding="utf-8") as f:
                rows = json.load(f)
            for row in rows:
                rel = row.get("xray_path")
                if not rel:
                    continue
                cand = os.path.join("chexpert", rel)
                if os.path.exists(cand):
                    return cand
        except Exception:
            pass

    fallback = [
        "chexpert/valid/patient64541/study1/view1_frontal.jpg",
        "chexpert/valid/patient64542/study1/view1_frontal.jpg",
    ]
    for p in fallback:
        if os.path.exists(p):
            return p
    return None


def generate_silent_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    frames = int(duration_sec * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 16-bit PCM
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def check_status(
    name: str,
    response: requests.Response,
    expected: Tuple[int, ...],
    extra_detail: str = "",
) -> StepResult:
    if response.status_code in expected:
        return StepResult(name=name, ok=True, detail=f"{response.status_code} {extra_detail}".strip())

    msg = ""
    try:
        body = response.json()
        msg = json.dumps(body)[:300]
    except Exception:
        msg = response.text[:300]
    return StepResult(name=name, ok=False, detail=f"{response.status_code} {msg}")


def http_smoke(args: argparse.Namespace, image_path: Optional[str]) -> List[StepResult]:
    out: List[StepResult] = []
    s = requests.Session()
    base = args.base_url.rstrip("/")
    timeout = args.timeout

    # 1) Health
    try:
        r = s.get(f"{base}/health", timeout=timeout)
        out.append(check_status("GET /health", r, (200,)))
    except Exception as e:
        out.append(StepResult("GET /health", False, str(e)))
        return out

    # 2) Infer
    try:
        payload = {"utterances": ["patient: chest discomfort and cough"]}
        r = s.post(f"{base}/infer", json=payload, timeout=timeout)
        res = check_status("POST /infer", r, (200,))
        if res.ok:
            data = r.json()
            for key in ("extraction", "answer", "summary"):
                if key not in data:
                    res = StepResult("POST /infer", False, f"missing key: {key}")
                    break
        out.append(res)
    except Exception as e:
        out.append(StepResult("POST /infer", False, str(e)))

    # 3) Image + multimodal/structured
    if image_path:
        try:
            with open(image_path, "rb") as f:
                files = {"file": (os.path.basename(image_path), f, "image/jpeg")}
                r = s.post(f"{base}/image_infer", files=files, timeout=timeout)
            res = check_status("POST /image_infer", r, (200,))
            if res.ok and "image_findings" not in r.json():
                res = StepResult("POST /image_infer", False, "missing key: image_findings")
            out.append(res)
        except Exception as e:
            out.append(StepResult("POST /image_infer", False, str(e)))

        try:
            with open(image_path, "rb") as f:
                files = {
                    "payload": (None, json.dumps({"utterances": ["patient: fever and cough"]}), "application/json"),
                    "file": (os.path.basename(image_path), f, "image/jpeg"),
                }
                r = s.post(f"{base}/multimodal_infer", files=files, timeout=timeout)
            res = check_status("POST /multimodal_infer", r, (200,))
            if res.ok:
                data = r.json()
                for key in ("fusion", "rag_advisory", "summary", "evidence"):
                    if key not in data:
                        res = StepResult("POST /multimodal_infer", False, f"missing key: {key}")
                        break
                if res.ok and "posterior_shift" not in (data.get("evidence") or {}):
                    res = StepResult("POST /multimodal_infer", False, "missing key: evidence.posterior_shift")
            out.append(res)
        except Exception as e:
            out.append(StepResult("POST /multimodal_infer", False, str(e)))

        try:
            with open(image_path, "rb") as f:
                files = {
                    "payload": (None, json.dumps({"utterances": ["patient: chest pain for one hour"]}), "application/json"),
                    "file": (os.path.basename(image_path), f, "image/jpeg"),
                }
                r = s.post(f"{base}/structured_diagnosis", files=files, timeout=timeout)
            res = check_status("POST /structured_diagnosis", r, (200,))
            if res.ok:
                data = r.json()
                for key in ("structured_diagnosis", "risk_analysis", "ehr_integration", "summary"):
                    if key not in data:
                        res = StepResult("POST /structured_diagnosis", False, f"missing key: {key}")
                        break
            out.append(res)
        except Exception as e:
            out.append(StepResult("POST /structured_diagnosis", False, str(e)))
    else:
        out.append(StepResult("image-dependent checks", False, "no local image found (set --image PATH)"))

    # 4) Voice transcribe
    if not args.skip_voice:
        try:
            wav = generate_silent_wav_bytes()
            files = {"file": ("smoke_silence.wav", wav, "audio/wav")}
            r = s.post(f"{base}/voice_transcribe", files=files, timeout=timeout)
            # 200 is expected; some stacks may return 400 if silence is rejected.
            res = check_status("POST /voice_transcribe", r, (200, 400))
            out.append(res)
        except Exception as e:
            out.append(StepResult("POST /voice_transcribe", False, str(e)))

    # 5) Case creation (HTTP side of live flow)
    try:
        r = s.post(f"{base}/api/case/voice?live=1", timeout=timeout)
        res = check_status("POST /api/case/voice", r, (200,))
        if res.ok and "case_id" not in r.json():
            res = StepResult("POST /api/case/voice", False, "missing key: case_id")
        out.append(res)
    except Exception as e:
        out.append(StepResult("POST /api/case/voice", False, str(e)))

    return out


def to_ws_url(base_url: str, case_id: str) -> str:
    p = urlparse(base_url)
    scheme = "wss" if p.scheme == "https" else "ws"
    return f"{scheme}://{p.netloc}/ws/case/{case_id}"


async def ws_check(base_url: str, case_id: str, timeout: int) -> StepResult:
    if websockets is None:
        return StepResult("WS /ws/case/{id}", False, "websockets package not installed")

    ws_url = to_ws_url(base_url, case_id)
    try:
        async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if not isinstance(first, dict):
                return StepResult("WS /ws/case/{id}", False, "first message is not JSON object")

            await ws.send(json.dumps({"utterance": "patient has chest pain", "speaker": "patient"}))
            second = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if not isinstance(second, dict):
                return StepResult("WS /ws/case/{id}", False, "second message is not JSON object")
            evidence = second.get("evidence") or {}
            if "posterior_shift" not in evidence:
                return StepResult("WS /ws/case/{id}", False, "missing key: evidence.posterior_shift")

            return StepResult("WS /ws/case/{id}", True, "connected + update received")
    except Exception as e:
        return StepResult("WS /ws/case/{id}", False, str(e))


def print_report(results: List[StepResult]) -> int:
    failed = [r for r in results if not r.ok]
    for r in results:
        tag = "PASS" if r.ok else "FAIL"
        print(f"[{tag}] {r.name}: {r.detail}")

    print()
    print(f"Summary: {len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


def main() -> int:
    args = parse_args()
    image_path = args.image or find_default_image_path()

    if image_path:
        print(f"Using image: {image_path}")
    else:
        print("No local image found; image-dependent checks may fail. Use --image PATH.")

    results = http_smoke(args, image_path)

    # Run websocket step using case_id from HTTP result if available.
    if not args.skip_ws:
        case_id = None
        try:
            r = requests.post(f"{args.base_url.rstrip('/')}/api/case/voice?live=1", timeout=args.timeout)
            if r.status_code == 200:
                case_id = r.json().get("case_id")
        except Exception:
            case_id = None

        if not case_id:
            results.append(StepResult("WS /ws/case/{id}", False, "could not create voice case_id"))
        else:
            ws_res = asyncio.run(ws_check(args.base_url.rstrip("/"), case_id, args.timeout))
            results.append(ws_res)

    return print_report(results)


if __name__ == "__main__":
    sys.exit(main())
