#!/usr/bin/env python3
"""Record real LLM responses into fixtures/llm/ for the replay tests.

Run with GEMINI_API_KEY (and optionally ANTHROPIC_API_KEY) set:

  python scripts/record_llm_fixtures.py

Each fixture keeps the raw response text plus metadata; the replay tests
(tests/test_llm_replay.py) then exercise the real post-processing against
what the models actually said. Without keys the script exits cleanly.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
FIXTURES = REPO_ROOT / "fixtures" / "llm"

STATE = {
    "top_candidates": [{"condition": "pneumonia_unspecified", "score": 0.62}],
    "extraction": {"symptoms": ["cough", "fever"], "duration": "3 days"},
    "top_confidence": 0.62,
    "margin": 0.1,
}


def _write(name: str, path: str, response: str, model: str) -> None:
    (FIXTURES / name).write_text(json.dumps({
        "_meta": {
            "synthetic": False,
            "path": path,
            "model": model,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "response": response,
    }, indent=2, ensure_ascii=False) + "\n")
    print(f"[record] {name} <- {model}")


def main() -> int:
    from core.llm_client import (anthropic_available, gemini_available,
                                 get_llm, get_live_model)

    if not gemini_available() and not anthropic_available():
        print("[record] no API keys configured; nothing recorded")
        return 0

    if gemini_available():
        from core import questioner_llm
        from core.config import render_prompt, load_allowed_labels

        lm = get_llm()
        q_prompt = (questioner_llm.SYSTEM + "\n\n" + questioner_llm.PROMPT.format(
            schema=json.dumps(questioner_llm.SCHEMA, indent=2),
            state=json.dumps(STATE)))
        _write("questioner_response.json", "propose_questions_llm",
               lm.invoke_json(q_prompt).content, lm.model)

        allowed = ", ".join(sorted(load_allowed_labels().get("issues_allowed", [])))
        a_prompt = render_prompt("answer", allowed_labels=allowed,
                                 extraction=json.dumps(STATE["extraction"]),
                                 context="(no context provided)")
        _write("answer_response.json", "answerer_generate",
               lm.invoke_json(a_prompt).content, lm.model)

        d_prompt = render_prompt("structured_diagnosis", allowed_labels=allowed,
                                 extraction=json.dumps(STATE["extraction"]),
                                 context="(no context provided)",
                                 ehr_context="", fusion_context="")
        _write("structured_diagnosis_response.json",
               "generate_structured_differential_diagnosis",
               lm.invoke_json(d_prompt).content, lm.model)
    else:
        print("[record] GEMINI_API_KEY absent; gemini-path fixtures kept as-is")

    if anthropic_available():
        from core.questioner_llm import stream_live_suggestions

        async def _collect() -> str:
            parts = []
            async for token in stream_live_suggestions(STATE):
                parts.append(token)
            return "".join(parts)

        _write("coach_stream_response.json",
               "stream_live_suggestions -> parse_bullet_questions",
               asyncio.run(_collect()), get_live_model())
    else:
        print("[record] ANTHROPIC_API_KEY absent; coach-stream fixture kept as-is")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
